# Topology Checker Design Specification

## Overview
The Topology Checker is a PyQGIS tool integrated into the `Gruhanaksha` plugin. It provides a comprehensive quality control suite for Polygon and MultiPolygon vector layers (such as land parcel and plinth shapefiles). It identifies topological errors and spatial anomalies comparable to ArcGIS Topology rules, using PyQGIS and GEOS geometry engine without any external dependencies.

---

## 1. Architecture & Plugin Integration
- **Framework**: Built strictly with Python standard library and PyQGIS APIs (`qgis.core`, `qgis.gui`, `qgis.PyQt`).
- **File Structure**:
  - `topology_checker.py`: Contains `TopologyCheckerDialog` (PyQt UI) and `TopologyEngine` (validation algorithms).
  - `tools.py`: Adds a **Topology Checker** button to the `ToolWidget` dialog grid.
  - `Gruhanaksha.py`: Integrates menu/toolbar hooks for launching the Topology Checker.
- **Dependencies**: No external Python packages required.

---

## 2. Topology Rules & Detection Logic

The tool runs the following topological checks:

1. **Must Be Valid Geometry (Self-Intersections & Structural Anomalies)**:
   - Identifies self-intersecting rings (bow-tie polygons), self-touching rings, inverted ring winding order, duplicate consecutive vertices, spikes/antennas, and unclosed polygon rings.
   - *Engine API*: `QgsGeometryEngine.isValid()`, `geometry.validateGeometry()`, and vertex inspection.

2. **Must Not Overlap**:
   - Identifies 2D interior overlap between any pair of polygons.
   - Calculates the exact overlapping area in layer units/m².
   - *Engine API*: Spatial candidate filtering via `QgsSpatialIndex`, GEOS intersection computation `geomA.intersection(geomB)`.

3. **Must Not Have Gaps / Slivers**:
   - Identifies voids or unmapped pockets between adjacent polygons that fall within a user-defined gap tolerance or area threshold.
   - *Engine API*: Difference calculations along shared boundaries and spatial index filtering.

4. **Must Not Have Duplicate Geometries**:
   - Detects features with identical coordinate sequences or 100% spatial equality.
   - *Engine API*: Spatial bounding hash + GEOS equality `geomA.equals(geomB)`.

5. **Must Not Be MultiPolygon (Singlepart Rule)**:
   - Flags features containing disjoint polygon parts when strict single-part parcel structure is required.
   - *Engine API*: `geometry.isMultipart()` and `geometry.numGeometries() > 1`.

6. **Micro-Polygon / Minimum Area Violation**:
   - Identifies polygons with total area below a configurable minimum threshold (e.g. < 0.01 m² digitizing artifacts).
   - *Engine API*: `geometry.area() < min_area_threshold`.

7. **Short Edges / Spike Vertices**:
   - Identifies edge segments shorter than a minimum segment length threshold.
   - *Engine API*: Distance calculations between adjacent boundary nodes.

---

## 3. User Interface & Interactive Map Inspection

- **Dialog (`TopologyCheckerDialog`)**:
  - **Layer Selector**: `QgsMapLayerComboBox` filtered to `QgsMapLayerProxyModel.PolygonLayer`.
  - **Rule Options**: Individual checkboxes for each topology rule.
  - **Tolerance Controls**: Spinboxes for Minimum Area Tolerance (m²), Overlap Tolerance (m²), and Gap Distance (m).
  - **Execution Controls**: "Run Topology Check" button, `QProgressBar`, and status messages.
  - **Results Table (`QTableWidget`)**:
    - Columns: `#`, `Feature ID(s)`, `Error Type`, `Description / Details`, `Location (X, Y)`.
    - Interactive sorting and filtering.
- **Canvas Interaction**:
  - **Single-Click / Row Selection**: Uses `QgsRubberBand` with a red highlight to trace the selected error geometry directly on the QGIS map canvas.
  - **Double-Click**: Automatically pans and zooms the QGIS map canvas to the bounding box of the error feature.
  - **Temporary Error Layer**: Creates a memory layer named `"Topology Error Markers"` containing error geometries and attributes for persistent visual inspection.

---

## 4. Error Reporting & Export Capabilities

- **Summary Cards**: Displays Total Features Checked, Total Errors Discovered, and Error Breakdown Counts by category.
- **CSV Export**: Exports error details including Feature IDs, Error Types, Descriptions, X/Y Coordinates, and Layer Name.
- **HTML Report Export**: Generates a formatted HTML report with summary stats, timestamp, layer metadata, and error details table.
- **Error Layer Export**: Option to save the temporary Error Memory Layer to a Shapefile or GeoPackage.
