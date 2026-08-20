---
sidebar_position: 17
keywords:
  - topology
  - checker
  - geometry
  - validation
  - quality control
  - sliver
  - gap
  - overlap
  - singlepart
tags: [topology, checker, validation, geometry, quality]
slug: topologychecker
---

# 🕵️‍♂️ Topology Checker Tool

`Available from v3.5.0`

:::info
The **Topology Checker** is a PyQGIS tool designed specifically to support SVAMITVA quality control guidelines. It identifies and corrects spatial errors and geometry anomalies, ensuring clean, contiguous, and valid vector datasets.
:::

## 🚀 Overview

The Topology Checker is an interactive validation suite that scans polygon and multipolygon vector layers (such as parcel boundary or plinth shapefiles) for geometric defects. Running directly on QGIS APIs, it identifies spatial errors such as overlaps, gaps, sliver polygons, and self-intersections. The tool is split into **Single Layer Checks** (intra-layer validation) and **Cross-Layer Checks** (inter-layer verification).

---

## 🗟 Interface Navigation

To open the tool, click the **Topology Checker** icon in the Gruhanaksha toolbar or panel. The dialog consists of:
- **Left Panel (Settings)**: Separated into two tabs: **Single Layer Checks** and **Cross-Layer Checks**.
- **Right Panel (Results Table)**: Displays identified errors, summary cards, and control buttons (Auto Fix, Export, Show Highlights).
- **Execution Bar**: A progress bar showing progress during validation tasks.

---

## 1. Single Layer Checks Tab

Use this tab to validate a single polygon layer against standard topological rules.

### ⚙️ Settings
- **Target Polygon Layer**: Combobox to select the layer to inspect.
- **Tolerances**:
  - **Minimum Area (m²)**: Threshold below which a polygon is considered a "Micro-Polygon".
  - **Overlap Area Limit (m²)**: Minimum overlapping area to flag.
  - **Gap Distance Limit (m)**: Maximum distance between adjacent boundaries to check for sliver gaps.

### 📐 Rules & Logic

1. **Must Be Valid Geometry (Self-Intersections)**
   - **What it catches**: bow-tie polygons, self-touching rings, inverted ring winding orders, duplicate consecutive vertices, and unclosed rings.
   - **Why it matters**: Invalid geometries can crash geoprocessing tools or cause inaccurate area calculations.
2. **Must Not Overlap**
   - **What it catches**: Places where two polygons share 2D interior space.
   - **Why it matters**: A parcel of land cannot belong to two properties simultaneously.
3. **Must Not Have Gaps / Slivers**
   - **What it catches**: Unmapped voids or narrow "sliver" pockets between adjacent polygons that fall within the *Gap Distance Limit*.
   - **Why it matters**: In a complete land survey, all parcels should touch seamlessly.
4. **Must Not Have Duplicate Geometries**
   - **What it catches**: Polygons with identical coordinate sequences or 100% spatial equality (even if coordinate winding direction is opposite or starting vertex is shifted).
   - **Why it matters**: Duplicate records cause double-counting in databases.
5. **Must Not Be MultiPolygon (Singlepart Rule)**
   - **What it catches**: Features containing disjoint polygon parts.
   - **Why it matters**: Parcels must be single contiguous shapes.
6. **Micro-Polygon / Minimum Area Violation**
   - **What it catches**: Polygons whose total area is below the *Minimum Area* tolerance (e.g., < 0.01 m²). These are usually digitization artifacts.
7. **Short Edges / Spike Vertices**
   - **What it catches**: Edge segments shorter than a minimum segment threshold or spike vertices creating "antennas" along boundaries.

---

## 2. Cross-Layer Checks Tab

Use this tab to identify gaps and overlaps between two different layers (e.g., comparing your parcel layer against a village boundary layer or a neighboring village survey).

### ⚙️ Settings
- **Main Polygon Layer**: Select your primary layer to inspect.
- **Other Polygon Layers**: A list of all other polygon layers in your project. Check the boxes next to the layers you want to compare against.
- **Rules & Tolerances**:
  - **Check Cross-Layer Overlaps** (with its own Overlap Area Tolerance in m²).
  - **Check Cross-Layer Gaps** (with its own Gap Distance Limit in meters).

---

## 👁️ Interactive Map Inspection

When you click **Run Topology Check**, the tool validates features asynchronously (keeping QGIS responsive). Discovered errors appear in the Results Table.

- **Single-Click Error Selection**: Highlight the error. The tool draws a **Red Outline** (`QgsRubberBand`) around the error geometry on the map canvas.
- **Overlap Previews**: When you select an "Overlap" error, the tool draws a **Green Dashed Outline** showing the proposed fix geometry (the geometry of the smaller polygon after subtracting the overlap).
- **Double-Click Row**: Instantly pans and zooms the QGIS map canvas to the bounding box of the error feature.
- **Show Highlights Checkbox**: Check or uncheck to show/hide the red highlights on the map while you perform edits.

---

## 🛠️ Automated Fixes (`TopologyFixer`)

For many common errors, the tool provides automated fixes. Select one or more error rows and click **Auto Fix**:

- **Sliver Polygon Fix**: Merges the sliver polygon into the adjacent neighbor polygon with which it shares the **longest boundary**, and deletes the original sliver feature.
- **Overlap Fix**: Subtracts the overlapping geometry from the **smaller** of the two overlapping polygons (preserving the larger polygon's shape).
- **Overshoot / Dangling Line Fix**: Automatically repairs the geometry (`makeValid`) and coerces it back to a clean polygon, stripping away dangling lines.
- **Invalid Geometry Fix**: Runs automated node repair to fix bow-ties and closed rings.
- **Multipart Fix**: Explodes the multipart feature into singlepart features.
- **Cross-Layer Overlap Fix**: Subtracts the overlapping portion from the **Main Polygon Layer** feature.

---

## 📊 Exports & Quality Reports

The tool provides multiple ways to export and share your quality control reports:

1. **HTML Report**: Click **Export HTML** to write a formatted quality control report containing summary statistics, execution timestamps, layers checked, and a detailed table of all remaining errors.
2. **CSV Log**: Click **Export CSV** to write a tabular log file of feature IDs, error types, coordinate coordinates, and error descriptions.
3. **Error Layer Export**: The red error markers are saved to a temporary memory layer named `Topology Error Markers`. You can export this layer to a GeoPackage or Shapefile for future reference.
