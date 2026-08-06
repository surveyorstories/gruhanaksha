---
sidebar_position: 13

keywords:
  - KMZ
  - Export
  - KML
  - Google Earth
  - GIS Export
  - Vector Export
  - gruhanaksha

tags: [kmz, export, kml, google earth, vector, gis]
slug: kmz
---

# 📤 KMZ Exporter

`Available from v2.1.0`

The KMZ Exporter is a powerful tool for exporting QGIS vector layers to KMZ format, compatible with Google Earth and other KML-supporting applications. It provides comprehensive control over symbology, labeling, and export options.

## 🚀 Getting Started

### ✅ Prerequisites

- QGIS with active vector layers (point, line, or polygon geometry)
- Layers must be loaded in the current project

### 🔧 Installation & Activation

1. Click on KMZ Exporter Icon in the toolbar
2. The KMZ Exporter dialog will open

## 🎮 Main Interface

### 📋 Layer Selection

- **Select All**: Check all available vector layers for export
- **Select None**: Uncheck all layers
- **Layer List**: Check/uncheck individual layers to include in export
- **Selected Only**: Option to export only selected features from each layer

### ⚙️ Layer Settings

Configure export settings for each layer individually:

#### 🏷️ Label Tab

**Label Display Options:**

- **Map**: Labels appear directly on the map in Google Earth.
- **Popup Only**: Labels are not on the map but appear in the feature's popup window.
- **Map + Popup**: Labels appear on the map and are also included at the top of the popup.
- **None**: No labels are exported for the layer.

**Label Fields (Multi-select):**

- Check one or more fields to combine into a single label.
- The order of selection does not matter; the fields are joined in their natural order.
- **Separator**: A character (or characters) to place between the values of the combined fields (default is " | ").

**Label Style:**

- **Size**: A scale factor to adjust the label size (0.5x to 5.0x).
- **Color**: The color of the label text.

#### 📝 Description Fields Tab

This tab controls which attribute fields are displayed in the feature's popup description in Google Earth.

- **Field List**: Check the boxes next to the fields you want to include.
- If **no fields are selected**, all fields will be automatically included in the description.
- Use the **Select All** and **Select None** buttons to quickly manage your selections.

#### 🎨 Symbology Tab

**QGIS Symbology:**

- **Use QGIS layer symbology**: Automatically export using current QGIS layer styling.
  - *Note: This dynamically supports layers styled with **Categorized Symbology** as well as single symbol renderers.*
- **Custom symbology**: Define custom styling for export.

**Custom Point Symbology:**

- **Icon**: Choose from predefined pushpin icons (Yellow, Red, Blue, Green) or select **"No Pin"** to export points without visual markers on the Google Earth map.
- **Size**: Scale factor for icon size (0.5x to 3.0x).
- **Color**: Icon color (when applicable).

**Custom Line Symbology:**

- **Width**: Line width in pixels (0.5 to 10.0)
- **Color**: Line color

**Custom Polygon Symbology:**

- **Fill color**: Interior fill color with alpha transparency
- **Outline width**: Border width in pixels
- **Outline color**: Border color

### 📁 Output Settings

- **Output Path**: Specify the KMZ file location
- **Browse**: Open file dialog to choose save location
- **Folder Link**: Click to open the output folder after export

## 📤 Export Process

1. Select layers to export
2. Configure label and symbology settings for each layer
3. Set output KMZ file path
4. Choose whether to export selected features only
5. Click **Export** to start the process

### 📊 Progress Tracking

- Real-time progress bar showing export completion
- Status messages for each processing step
- Cancel button to stop export if needed

## 🎯 Export Features

### 🌍 Coordinate Transformation

- Automatically transforms all layers to WGS84 (EPSG:4326) for Google Earth compatibility
- Handles different source coordinate systems seamlessly

### 📋 Feature Processing

- **Point Features**: Exported as placemarks with icons
- **Line Features**: Exported as paths with customizable styling
- **Polygon Features**: Exported as filled polygons with labels positioned at centroid or pole of inaccessibility

### 🏷️ Smart Labeling

- **Automatic Field Detection**: Uses layer labeling settings or first suitable text field
- **HTML Descriptions**: Rich attribute tables in popup balloons
- **Label Positioning**: Optimal placement for polygon centroids

### 🎨 Symbology Preservation

- **QGIS Integration**: Direct export of existing layer styles
- **Custom Overrides**: Full control over export appearance
- **Color Management**: Proper color conversion for KML format

## 📝 Workflow Examples

### 🏗️ Example 1: Basic Layer Export

```
1. Open KMZ Exporter dialog
2. Check the layers you want to export
3. For each layer, choose label display option
4. Set output KMZ file path
5. Click Export
6. Open the KMZ in Google Earth
```

### 🏗️ Example 2: Custom Styled Export

```
1. Select target layers
2. For each layer:
   - Uncheck "Use QGIS layer symbology"
   - Customize colors, sizes, and styles
   - Choose label field and styling
3. Set output path
4. Export and view in Google Earth
```

### 🏗️ Example 3: Selected Features Only

```
1. Select specific features in your QGIS layers
2. Open KMZ Exporter
3. Check "Export only selected features"
4. Configure settings as needed
5. Export selected features to KMZ
```

## ⚠️ Troubleshooting

### 🔴 Common Issues

**No layers available:**

- Ensure you have vector layers loaded in your QGIS project
- Check that layers are not hidden in the layer tree

**Export fails:**

- Verify output folder exists and is writable
- Check that selected layers have valid geometries
- Ensure sufficient disk space for KMZ file

**Labels not showing:**

- Confirm label field exists and has data
- Check label display settings (on map vs popup)
- Verify label color contrasts with background

**Symbology issues:**

- Try toggling "Use QGIS layer symbology" on/off
- Check custom color settings for validity
- Ensure polygon fill opacity is not set to 0%

### 💡 Tips for Best Results

1. **Layer Preparation**: Clean up geometries before export
2. **Label Fields**: Choose descriptive field names for labels
3. **Color Contrast**: Ensure label colors are visible against symbology
4. **File Size**: Large datasets may create big KMZ files
5. **Google Earth**: Test exports in Google Earth for final appearance

## 📋 Technical Details

### 🗂️ KMZ Structure

- **doc.kml**: Main KML document with all features and styling
- **Compressed**: ZIP-compressed for efficient storage and transfer

### 🎨 KML Compatibility

- **Google Earth**: Full compatibility with all features
- **Other Viewers**: Compatible with most KML-supporting applications
- **Standards**: Follows OGC KML 2.2 specification

### 📊 Performance Considerations

- **Large Datasets**: Export time scales with feature count
- **Complex Geometries**: Multipart features may increase processing time
- **Network Links**: Consider using for very large datasets

## 🔗 Related Tools

- **QGIS Native Export**: For other GIS formats
- **Google Earth Pro**: For advanced visualization
- **Other KML Tools**: For specialized KML editing
