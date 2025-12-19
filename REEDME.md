# 🗺️ Interactive Cadastral Map Generator

**A Python tool to visualize Spanish land parcels ("fincas") on an interactive map using official Cadastral data.**

> 👵 **Story:** This project was originally designed for my grandmother in Galicia to help her visualize and manage her terrains easily on her mobile phone. It simplifies complex cadastral data into a clean, color-coded map.
> It proved so useful that I successfully used this same script to map the terrains for all my neighbors in the village—proving it works for anyone just by swapping the Excel data.

>Note on Privacy: The cadastral references in the provided Excel file are for demonstration purposes only. All sensitive data has been replaced with sample data to protect my family's privacy.
If there's a bug/error might be because the number refrences were genreated rendomly.

## ✨ Features

* **📱 Fully Responsive:** The generated map works perfectly on Mobiles, Tablets, and Desktop. Includes a slide-up panel for mobile devices.
* **🇪🇸 Official Data:** Connects directly to the [Spanish Cadastre (Sede Electrónica)](https://www.sedecatastro.gob.es/) via WFS API to fetch precise geometry and coordinates.
* **⚡ Fast Processing:** Uses multi-threading to process lists of properties quickly.
* **🎨 Custom Visualization:** Color-code your terrains based on their type (e.g., "Matorral", "Prado", "Urbano").
* **📊 Statistics:** Automatically calculates total area (m² or hectares) and groups data by type.
* **🔍 Searchable:** Includes a built-in search bar to find parcels by name or reference.
* **🔄 Reusable & Community Tested:** Designed to be flexible. You can generate a new map for any user just by modifying the Excel file.

## 🚀 How to Use

If you cannot open the .html file on your mobile device (e.g., iPhone) Android should be fine, you may need an HTML viewer. Recommended apps include Documents by Readdle or HTML Viewer Q.

### 1. Prerequisites
You need Python installed. Install the dependencies:

```bash
pip install pandas requests openpyxl
python script.py
