---
sidebar_position: 18
keywords:
  - traverse
  - plotter
  - survey
  - bearing
  - distance
  - links
  - bowditch
tags: [traverse, plotter, survey, bearing, distance, bowditch]
slug: traverseplotter
---

# 🗺️ Traverse Plotter Tool

`Available from v3.6.0`

:::info
The **Traverse Plotter** is an interactive survey utility designed to plot polyline or polygon traverses directly from field survey sheets containing bearings, angles, and distances.
:::

## 🚀 Overview

The Traverse Plotter translates classic surveyor notes (such as Azimuth/Bearing, Angle-to-Right, or Deflection angles) and linear measurements (in Links, Feet, or Meters) into geographic vector layers in QGIS. It includes full support for closed traverses and coordinates adjustment using the Bowditch Compass Rule.

---

## 🪟 Interface Layout

To launch the tool:
1. Open the Gruhanaksha **Tools Panel** from the toolbar or menu.
2. Click the **Traverse Plotter** button.
3. The Traverse Plotter window will open, organized into four key sections.

---

## 1. Starting Parameters

Define where the traverse starts and the initial reference direction:
- **Start X (Easting) & Start Y (Northing)**: Enter the starting coordinates manually in project CRS units.
- **Pick on Canvas**: Click this button, then left-click anywhere on the QGIS map canvas to automatically grab and load the coordinates of the clicked location.
- **Initial Bearing**: Reference direction in decimal degrees (measured clockwise from North, where North = 0°) for the starting segment of the traverse.

---

## 2. Plotting Settings

Configure how angles and distances are parsed:

### 📐 Angle Input Mode
- **Azimuth / Bearing**: Absolute angle measured clockwise from North (0° to 360°) for each line segment.
- **Angle to Right (Clockwise)**: Relative angle measured clockwise from the back-sight line (the extension of the previous segment flipped 180°).
- **Deflection Angle**: Relative angle turned Left (negative values) or Right (positive values) from the extension of the previous segment.

### 🔣 Angle Format
- **Decimal Degrees / Spaced DMS**: Input decimal degree values (e.g., `136.5`) or space-separated degrees, minutes, and seconds (e.g., `136 30 15` for $136^{\circ} 30' 15''$).
- **DD.MMSS / DD.MM (Surveyor DMS)**: Traditional surveyor notation where the digits after the decimal represent minutes and seconds (e.g., `136.0230` represents $136^{\circ} 02' 30''$ and `136.02` represents $136^{\circ} 02'$). The tool parses and converts this format automatically.

### 📏 Distance Unit
Choose the unit for distances entered in the table:
- **Gunter's Links** (1 Link = 0.201168 meters)
- **Meters** (1.0 meter)
- **Feet** (0.3048 meters)
- **Metric Links** (1 Link = 0.2 meters)

*Note: Distances are automatically converted to project CRS coordinates during plotting.*

### 🔒 Closure & Adjustments
- **Draw as Closed Polygon**: Connects the final station back to the starting coordinate (Station A) to form a closed polygon geometry rather than a polyline.
- **Apply Bowditch Adjustment**: Applies the Compass Rule (Bowditch method) to distribute linear closure errors (difference between the starting point and the calculated final point of a closed traverse) proportionally across each course according to its length.

---

## 3. Traverse Courses Table

Input individual courses in the spreadsheet table:
- **Columns**:
  - **From**: Starting station name (defaults to alphabetically auto-incremented letters: A, B, C...).
  - **To**: Destination station name (defaults to B, C, D...).
  - **Angle**: The angle value based on the chosen *Angle Input Mode* and *Angle Format*.
  - **Distance**: The segment length in the selected *Distance Unit*.
- **Controls**:
  - **Add Row**: Inserts a new row with auto-incremented station names.
  - **Remove Row**: Removes the currently selected row or the last row.
  - **Clear**: Completely clears the table and populates it with 4 empty default rows.

---

## 4. Plotting Traverse to QGIS

Once all courses are entered in the table, click **Plot Traverse**:
1. The tool calculates coordinates of each station sequentially.
2. If Bowditch adjustment is enabled, it distributes the closure error.
3. It creates **two new memory layers** in your QGIS project:
   - **`Survey Traverse`**: A line or polygon geometry representing the path.
   - **`Traverse Stations`**: A point layer representing station markers (A, B, C...) with text labels.
4. Both layers are added to the QGIS map legend and rendered on the map canvas.
