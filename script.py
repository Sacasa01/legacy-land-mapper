#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GENERADOR DE MAPAS CATASTRALES INTERACTIVOS (Versión 3.1 - Responsive Móvil)
---------------------------------------------------------
Autor: Tu Asistente de IA
Mejoras: Totalmente responsive para móvil con panel inferior deslizable
"""

import pandas as pd
import requests
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time
import sys

# --- CONFIGURACIÓN DE RENDIMIENTO ---
MAX_WORKERS = 20
TIMEOUT = 30
MAX_RETRIES = 3

def limpiar_consola():
    print("\033[H\033[J", end="")

def validar_excel(df):
    errores = []
    df.columns = [c.strip().lower() for c in df.columns]
    required_cols = ['referencia', 'tipo', 'nombre', 'color']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        return False, f"Faltan las columnas: {', '.join(missing)}"
    return True, "Estructura correcta"

def obtener_geometria_catastro(referencia_catastral, nombre_log=""):
    ref_corta = referencia_catastral[:14]
    url = "http://ovc.catastro.meh.es/INSPIRE/wfsCP.aspx"
    params = {
        'service': 'WFS', 'version': '2', 'request': 'GetFeature',
        'STOREDQUERIE_ID': 'GetParcel', 'refcat': ref_corta,
        'srsname': 'EPSG::4326'
    }
    ns = {
        'gml': 'http://www.opengis.net/gml/3.2',
        'cp': 'http://inspire.ec.europa.eu/schemas/cp/4.0',
        'gn': 'http://inspire.ec.europa.eu/schemas/gn/4.0'
    }

    for intento in range(MAX_RETRIES):
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            
            area_elem = root.find('.//cp:areaValue', ns)
            area_m2 = float(area_elem.text) if area_elem is not None else 0
            
            municipio = "Desconocido"
            muni_elem = root.find('.//gn:text', ns)
            if muni_elem is not None: municipio = muni_elem.text
            
            pos_list = root.find('.//gml:posList', ns)
            if pos_list is not None:
                coords_text = pos_list.text.strip()
                coords_array = coords_text.split()
                coordinates = []
                for i in range(0, len(coords_array), 2):
                    lat = float(coords_array[i])
                    lon = float(coords_array[i+1])
                    coordinates.append([lon, lat])
                return coordinates, area_m2, municipio, None
            else:
                return None, 0, municipio, "Geometría no encontrada"

        except requests.exceptions.RequestException:
            if intento < MAX_RETRIES - 1:
                time.sleep(1)
                continue
            else:
                return None, 0, "Error Red", "Fallo tras reintentos"
        except Exception as e:
            return None, 0, "Error", str(e)
            
    return None, 0, "Error", "Error desconocido"

def procesar_fila(idx, row):
    ref = str(row['referencia']).strip()
    nombre = str(row['nombre']).strip()
    coords, area, muni, err = obtener_geometria_catastro(ref, nombre)
    
    if coords:
        return {
            "type": "Feature",
            "properties": {
                "ref": ref,
                "tipo": str(row['tipo']).strip(),
                "nombre": nombre,
                "color": str(row['color']).strip(),
                "area_m2": area,
                "municipio": muni
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [coords]
            }
        }, None
    else:
        return None, f"{nombre} ({ref}): {err}"

def generar_html_final(geojson_data, nombre_cliente, errores):
    json_str = json.dumps(geojson_data, ensure_ascii=False)
    fecha = datetime.now().strftime("%d/%m/%Y")
    
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Mapa de Fincas - {nombre_cliente}</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" />
    <style>
        * {{ box-sizing: border-box; }}
        body {{ margin: 0; padding: 0; font-family: 'Segoe UI', Helvetica, sans-serif; overflow: hidden; }}
        #map {{ height: 100vh; width: 100%; }}
        
        /* --- BOTÓN PARA MOSTRAR/OCULTAR PANEL --- */
        .toggle-panel-btn {{
            position: absolute;
            top: 20px;
            left: 20px;
            z-index: 1001;
            background: white;
            border: none;
            width: 50px;
            height: 50px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.2);
            cursor: pointer;
            font-size: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.3s;
        }}
        
        .toggle-panel-btn:hover {{
            background: #f0f0f0;
        }}
        
        /* --- PANEL IZQUIERDO (DESKTOP) --- */
        .info-panel {{
            position: absolute; 
            top: 20px; 
            left: 80px;
            z-index: 1000;
            background: white; 
            padding: 20px; 
            border-radius: 12px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15); 
            width: 320px;
            max-height: 90vh; 
            overflow-y: auto;
            border: 1px solid rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }}
        
        .info-panel.hidden {{
            transform: translateX(-420px);
            opacity: 0;
            pointer-events: none;
        }}
        
        .header-box {{ border-bottom: 1px solid #eee; padding-bottom: 15px; margin-bottom: 20px; }}
        h1 {{ margin: 0; font-size: 22px; color: #1a1a1a; font-weight: 700; }}
        .subtitle {{ color: #666; font-size: 13px; margin-top: 5px; }}
        
        /* Estadísticas */
        .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 25px; }}
        .stat-card {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; border: 1px solid #eee; }}
        .stat-val {{ display: block; font-weight: 800; color: #2c3e50; font-size: 20px; }}
        .stat-label {{ font-size: 11px; color: #888; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 5px; }}
        
        /* Buscador */
        .search-box {{ position: relative; margin-bottom: 20px; }}
        .search-input {{ 
            width: 100%; padding: 12px; border: 1px solid #e0e0e0; 
            border-radius: 8px; box-sizing: border-box; font-size: 14px; transition: all 0.2s;
        }}
        .search-input:focus {{ outline: none; border-color: #3498db; box-shadow: 0 0 0 3px rgba(52,152,219,0.1); }}
        .search-results {{ 
            max-height: 200px; overflow-y: auto; border: 1px solid #eee; 
            display: none; margin-top: 5px; border-radius: 8px; background: white;
            position: absolute; width: 100%; z-index: 2000; box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        }}
        .result-item {{ padding: 10px 15px; cursor: pointer; border-bottom: 1px solid #f5f5f5; font-size: 13px; }}
        .result-item:hover {{ background: #f8f9fa; color: #3498db; }}
        
        /* Filtros */
        .filter-section {{ border-top: 1px solid #eee; padding-top: 20px; }}
        .filter-btn {{ 
            display: flex; align-items: center; justify-content: space-between; width: 100%; padding: 10px; margin: 6px 0; 
            border: 1px solid #eee; background: white; cursor: pointer; 
            border-radius: 6px; text-align: left; font-size: 13px; color: #444; transition: all 0.2s;
        }}
        .filter-btn:hover {{ background: #f4f6f7; border-color: #d0d0d0; }}
        .filter-btn-left {{ display: flex; align-items: center; }}
        .filter-btn-right {{ font-size: 12px; color: #888; font-weight: 600; }}
        .color-dot {{ display: inline-block; width: 12px; height: 12px; border-radius: 50%; margin-right: 10px; }}
        
        /* --- POPUP MEJORADO --- */
        .leaflet-popup-content-wrapper {{ border-radius: 8px; box-shadow: 0 3px 14px rgba(0,0,0,0.2); padding: 0; overflow: hidden; }}
        .leaflet-popup-content {{ margin: 0; width: 280px !important; }}
        
        .popup-header-clean {{ 
            padding: 15px 20px; 
            background: #fff; 
            border-bottom: 2px solid #f0f0f0;
        }}
        .popup-title {{ font-size: 16px; font-weight: 700; color: #2c3e50; margin: 0; }}
        .popup-type-badge {{ 
            font-size: 11px; text-transform: uppercase; background: #eee; 
            padding: 2px 6px; border-radius: 4px; color: #666; margin-top: 5px; display: inline-block;
        }}
        
        .popup-body {{ padding: 15px 20px; background: #fff; }}
        .data-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 13px; color: #555; }}
        .data-label {{ font-weight: 600; color: #999; }}
        .data-value {{ color: #333; font-family: monospace; }}
        
        .cadastre-link {{
            display: block; text-align: center; margin-top: 15px; padding: 8px;
            background: #e8f4fc; color: #3498db; text-decoration: none;
            border-radius: 6px; font-size: 12px; font-weight: 600; transition: background 0.2s;
        }}
        .cadastre-link:hover {{ background: #d1e8fa; }}
        
        /* Control de Capas Simple */
        .layer-toggle {{ 
            position: absolute; top: 20px; right: 20px; z-index: 1000; 
            background: white; padding: 10px 15px; border-radius: 8px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); font-size: 13px; font-weight: 600;
            display: flex; align-items: center; gap: 8px;
        }}
        
        /* --- RESPONSIVE MÓVIL --- */
        @media (max-width: 768px) {{
            .toggle-panel-btn {{
                top: 10px;
                left: 10px;
                width: 45px;
                height: 45px;
                font-size: 20px;
                z-index: 1002;
            }}
            
            /* Panel inferior deslizable en móvil */
            .info-panel {{
                position: fixed;
                top: auto;
                bottom: 0;
                left: 0;
                right: 0;
                width: 100%;
                max-height: 75vh;
                border-radius: 20px 20px 0 0;
                padding: 20px 15px 15px;
                transform: translateY(0);
                opacity: 1;
                pointer-events: all;
                box-shadow: 0 -4px 20px rgba(0,0,0,0.2);
            }}
            
            .info-panel.hidden {{
                transform: translateY(calc(100% - 70px));
            }}
            
            /* Indicador visual de deslizamiento */
            .info-panel::before {{
                content: '';
                position: absolute;
                top: 8px;
                left: 50%;
                transform: translateX(-50%);
                width: 40px;
                height: 5px;
                background: #ccc;
                border-radius: 3px;
            }}
            
            .header-box {{
                margin-top: 15px;
                padding-bottom: 12px;
                margin-bottom: 15px;
            }}
            
            h1 {{
                font-size: 18px;
            }}
            
            .subtitle {{
                font-size: 12px;
            }}
            
            .stat-grid {{
                gap: 10px;
                margin-bottom: 15px;
            }}
            
            .stat-card {{
                padding: 12px;
            }}
            
            .stat-val {{
                font-size: 18px;
            }}
            
            .stat-label {{
                font-size: 10px;
            }}
            
            .search-input {{
                padding: 10px;
                font-size: 14px;
            }}
            
            .filter-btn {{
                padding: 12px;
                margin: 8px 0;
            }}
            
            .layer-toggle {{
                top: 10px;
                right: 10px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            
            /* Ajustar popups en móvil */
            .leaflet-popup-content {{
                width: 250px !important;
            }}
            
            .popup-header-clean {{
                padding: 12px 15px;
            }}
            
            .popup-title {{
                font-size: 15px;
            }}
            
            .popup-body {{
                padding: 12px 15px;
            }}
            
            .data-row {{
                font-size: 12px;
            }}
        }}
        
        /* Para pantallas muy pequeñas */
        @media (max-width: 400px) {{
            .info-panel {{
                max-height: 80vh;
            }}
            
            .stat-grid {{
                grid-template-columns: 1fr;
            }}
            
            h1 {{
                font-size: 16px;
            }}
            
            .toggle-panel-btn {{
                width: 40px;
                height: 40px;
                font-size: 18px;
            }}
        }}
    </style>
</head>
<body>

<div id="map"></div>

<!-- Botón para mostrar/ocultar panel -->
<button class="toggle-panel-btn" id="togglePanelBtn" onclick="togglePanel()">
    ☰
</button>

<div class="info-panel hidden" id="infoPanel">
    <div class="header-box">
        <h1>{nombre_cliente}</h1>
        <div class="subtitle">Patrimonio Inmobiliario • {fecha}</div>
    </div>
    
    <div class="stat-grid">
        <div class="stat-card">
            <span class="stat-val" id="total-fincas">0</span>
            <span class="stat-label">Parcelas</span>
        </div>
        <div class="stat-card">
            <span class="stat-val" id="total-area">0 ha</span>
            <span class="stat-label">Superficie</span>
        </div>
    </div>
    
    <div class="search-box">
        <input type="text" id="searchInput" class="search-input" placeholder="🔍 Buscar parcela...">
        <div id="searchResults" class="search-results"></div>
    </div>
    
    <div class="filter-section">
        <h4 style="margin: 0 0 15px 0; font-size: 12px; color: #999; text-transform: uppercase;">Filtrar por Tipo</h4>
        <div id="filterContainer"></div>
    </div>
</div>

<div class="layer-toggle">
    <input type="checkbox" id="toggleCatastro" checked>
    <label for="toggleCatastro" style="cursor:pointer">Catastro</label>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
    // DATOS
    const data = {json_str};
    
    // Variables para control táctil en móvil
    let startY = 0;
    let currentY = 0;
    let isDragging = false;
    
    // FUNCIÓN PARA FORMATEAR ÁREA
    function formatArea(area_m2) {{
        if (area_m2 >= 10000) {{
            return (area_m2 / 10000).toFixed(2) + ' ha';
        }} else {{
            return Math.round(area_m2).toLocaleString() + ' m²';
        }}
    }}
    
    // FUNCIÓN PARA MOSTRAR/OCULTAR PANEL
    function togglePanel() {{
        const panel = document.getElementById('infoPanel');
        panel.classList.toggle('hidden');
    }}
    
    // GESTOS TÁCTILES PARA MÓVIL (Deslizar panel)
    if (window.innerWidth <= 768) {{
        const panel = document.getElementById('infoPanel');
        
        panel.addEventListener('touchstart', (e) => {{
            startY = e.touches[0].clientY;
            isDragging = true;
        }}, {{ passive: true }});
        
        panel.addEventListener('touchmove', (e) => {{
            if (!isDragging) return;
            currentY = e.touches[0].clientY;
            const diff = currentY - startY;
            
            // Solo permitir deslizar hacia abajo cuando está arriba
            if (diff > 0 && !panel.classList.contains('hidden')) {{
                e.preventDefault();
            }}
        }}, {{ passive: false }});
        
        panel.addEventListener('touchend', (e) => {{
            if (!isDragging) return;
            isDragging = false;
            
            const diff = currentY - startY;
            
            // Si desliza más de 50px hacia abajo, ocultar
            if (diff > 50 && !panel.classList.contains('hidden')) {{
                panel.classList.add('hidden');
            }}
            // Si desliza más de 50px hacia arriba, mostrar
            else if (diff < -50 && panel.classList.contains('hidden')) {{
                panel.classList.remove('hidden');
            }}
        }});
    }}
    
    // INICIALIZAR MAPA
    const map = L.map('map', {{
        zoomControl: false
    }}).setView([40.416, -3.703], 6);
    
    // Añadir zoom en posición responsive
    const zoomPosition = window.innerWidth <= 768 ? 'bottomright' : 'bottomright';
    L.control.zoom({{ position: zoomPosition }}).addTo(map);
    
    // CAPAS
    const satelite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
        attribution: 'Esri', maxZoom: 20
    }}).addTo(map);
    
    L.tileLayer('https://{{s}}.basemaps.cartocdn.com/light_only_labels/{{z}}/{{x}}/{{y}}{{r}}.png', {{
        pane: 'shadowPane'
    }}).addTo(map);
    
    const catastroLayer = L.tileLayer.wms('http://ovc.catastro.meh.es/Cartografia/WMS/ServidorWMS.aspx', {{
        layers: 'Catastro', format: 'image/png', transparent: true, opacity: 0.6, zIndex: 10
    }}).addTo(map);
    
    // Toggle Catastro
    document.getElementById('toggleCatastro').addEventListener('change', function(e) {{
        if(e.target.checked) {{ map.addLayer(catastroLayer); }}
        else {{ map.removeLayer(catastroLayer); }}
    }});

    // ESTILOS Y GEOJSON
    let geoJsonLayer;
    
    function style(feature) {{
        return {{
            fillColor: feature.properties.color,
            weight: 2,
            opacity: 1,
            color: 'white',
            dashArray: '',
            fillOpacity: 0.55
        }};
    }}

    function highlightFeature(e) {{
        var layer = e.target;
        layer.setStyle({{ weight: 4, color: '#f1c40f', fillOpacity: 0.8 }});
        layer.bringToFront();
    }}

    function resetHighlight(e) {{ geoJsonLayer.resetStyle(e.target); }}

    function onEachFeature(feature, layer) {{
        layer.on({{ mouseover: highlightFeature, mouseout: resetHighlight }});
        
        const p = feature.properties;
        const refFull = p.ref;
        const del = refFull.substring(0, 2); 
        const mun = refFull.substring(2, 5);
        const ref14 = refFull.substring(0, 14);
        
        const urlCatastro = `https://www1.sedecatastro.gob.es/Cartografia/mapa.aspx?refcat=${{ref14}}&from=OVCBusqueda&RCCompleta=${{refFull}}&del=${{del}}&mun=${{mun}}`;
        
        const popupContent = `
            <div class="popup-header-clean">
                <div class="popup-title">${{p.nombre}}</div>
                <div class="popup-type-badge" style="border: 1px solid ${{p.color}}; color: ${{p.color}}">${{p.tipo}}</div>
            </div>
            <div class="popup-body">
                <div class="data-row">
                    <span class="data-label">Ref. Catastral</span>
                    <span class="data-value">${{p.ref.substring(0,14)}}...</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Superficie</span>
                    <span class="data-value">${{formatArea(p.area_m2)}}</span>
                </div>
                <div class="data-row">
                    <span class="data-label">Municipio</span>
                    <span class="data-value">${{p.municipio}}</span>
                </div>
                <a href="${{urlCatastro}}" target="_blank" class="cadastre-link">
                    <i class="fas fa-external-link-alt"></i> Ver en Catastro
                </a>
            </div>
        `;
        layer.bindPopup(popupContent, {{ maxWidth: 300 }});
    }}

    // CARGAR DATOS
    geoJsonLayer = L.geoJSON(data, {{
        style: style,
        onEachFeature: onEachFeature
    }}).addTo(map);

    if (data.features.length > 0) map.fitBounds(geoJsonLayer.getBounds(), {{ padding: [50, 50] }});

    // --- LÓGICA DE NEGOCIO ---
    
    // 1. Calcular áreas por tipo
    const areasPorTipo = {{}};
    data.features.forEach(f => {{
        const tipo = f.properties.tipo;
        if (!areasPorTipo[tipo]) {{
            areasPorTipo[tipo] = 0;
        }}
        areasPorTipo[tipo] += f.properties.area_m2 || 0;
    }});
    
    // 2. Estadísticas generales
    const totalArea = data.features.reduce((acc, f) => acc + (f.properties.area_m2 || 0), 0);
    document.getElementById('total-fincas').innerText = data.features.length;
    document.getElementById('total-area').innerText = formatArea(totalArea);

    // 3. Filtros Dinámicos con superficies
    const types = [...new Set(data.features.map(f => f.properties.tipo))].sort();
    const container = document.getElementById('filterContainer');
    
    // Botón "Todos" con superficie total
    const btnAll = document.createElement('div');
    btnAll.className = 'filter-btn';
    btnAll.innerHTML = `
        <div class="filter-btn-left">
            <span class="color-dot" style="background:#333"></span>
            <span>Ver Todo</span>
        </div>
        <span class="filter-btn-right">${{formatArea(totalArea)}}</span>
    `;
    btnAll.onclick = () => {{ 
        geoJsonLayer.clearLayers(); 
        geoJsonLayer.addData(data); 
        map.fitBounds(geoJsonLayer.getBounds()); 
    }};
    container.appendChild(btnAll);

    types.forEach(type => {{
        const feats = data.features.filter(f => f.properties.tipo === type);
        const color = feats[0].properties.color;
        const areaTotal = areasPorTipo[type];
        
        const btn = document.createElement('div');
        btn.className = 'filter-btn';
        btn.innerHTML = `
            <div class="filter-btn-left">
                <span class="color-dot" style="background:${{color}}"></span>
                <span>${{type}}</span>
            </div>
            <span class="filter-btn-right">${{formatArea(areaTotal)}}</span>
        `;
        btn.onclick = () => {{
            geoJsonLayer.clearLayers();
            geoJsonLayer.addData(feats);
            if(feats.length > 0) map.fitBounds(geoJsonLayer.getBounds());
        }};
        container.appendChild(btn);
    }});

    // 4. Buscador
    const searchInput = document.getElementById('searchInput');
    const resultsBox = document.getElementById('searchResults');
    
    searchInput.addEventListener('input', (e) => {{
        const term = e.target.value.toLowerCase();
        resultsBox.innerHTML = '';
        if(term.length < 2) {{ resultsBox.style.display = 'none'; return; }}
        
        const matches = data.features.filter(f => 
            f.properties.nombre.toLowerCase().includes(term) || 
            f.properties.ref.toLowerCase().includes(term)
        );
        
        if(matches.length > 0) {{
            resultsBox.style.display = 'block';
            matches.slice(0,8).forEach(m => {{ 
                const div = document.createElement('div');
                div.className = 'result-item';
                div.innerHTML = `<b>${{m.properties.nombre}}</b> - <small>${{m.properties.ref}}</small>`;
                div.onclick = () => {{
                    geoJsonLayer.eachLayer(layer => {{
                        if(layer.feature.properties.ref === m.properties.ref) {{
                            map.flyTo(layer.getBounds().getCenter(), 18);
                            layer.openPopup();
                        }}
                    }});
                    resultsBox.style.display = 'none';
                    searchInput.value = '';
                }};
                resultsBox.appendChild(div);
            }});
        }} else {{
             resultsBox.style.display = 'none';
        }}
    }});
    
    // Cerrar buscador si clic fuera
    document.addEventListener('click', (e) => {{
        if (!searchInput.contains(e.target) && !resultsBox.contains(e.target)) {{
            resultsBox.style.display = 'none';
        }}
    }});

</script>
</body>
</html>"""
    return html

def main():
    limpiar_consola()
    print("="*60)
    print("   GENERADOR DE MAPAS CATASTRALES | V3.1 RESPONSIVE")
    print("="*60)

    cliente = input("👤 Nombre del Cliente: ").strip() or "Cliente"
    
    archivos = ['fincas2.xlsx', 'fincas2.csv']
    archivo_input = next((f for f in archivos if Path(f).exists()), None)
    
    if not archivo_input:
        print("\n❌ ERROR: No encuentro 'fincas2.xlsx' ni 'fincas2.csv'.")
        return

    print(f"\n📂 Procesando archivo: {archivo_input}")
    
    try:
        if archivo_input.endswith('.csv'):
            df = pd.read_csv(archivo_input)
        else:
            df = pd.read_excel(archivo_input)
            
        ok, msg = validar_excel(df)
        if not ok:
            print(f"❌ Error en Excel: {msg}")
            return
            
    except Exception as e:
        print(f"❌ Error leyendo archivo: {e}")
        return

    print(f"🚀 Iniciando ({MAX_WORKERS} hilos)... Objetivo: {len(df)} parcelas\n")
    
    features = []
    errores = []
    completados = 0
    total = len(df)
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(procesar_fila, i, row): row for i, row in df.iterrows()}
        
        for future in as_completed(futures):
            res, err = future.result()
            completados += 1
            sys.stdout.write(f"\r⏳ Progreso: {completados}/{total} ({(completados/total)*100:.1f}%)")
            sys.stdout.flush()
            
            if res:
                features.append(res)
            else:
                errores.append(err)

    print("\n\n✅ Procesamiento finalizado.")
    
    if not features:
        print("❌ No se pudo recuperar ninguna parcela válida.")
        return

    geojson_collection = {"type": "FeatureCollection", "features": features}
    html_content = generar_html_final(geojson_collection, cliente, errores)
    nombre_salida = f"Mapa_{cliente.replace(' ','_')}.html"
    
    with open(nombre_salida, "w", encoding="utf-8") as f:
        f.write(html_content)
        
    print("="*60)
    print(f"🎉 ARCHIVO GENERADO: {nombre_salida}")
    print(f"   - Parcelas OK: {len(features)}")
    print(f"   - Errores: {len(errores)}")
    print(f"   - ✨ Ahora es 100% RESPONSIVE para móvil")
    print("="*60)

if __name__ == "__main__":
    main()