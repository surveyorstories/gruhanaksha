# Design Specification: Documentation Updates for Gruhanaksha 3.6.0

This design specification details updates to the user documentation of the `Gruhanaksha` QGIS plugin. It covers modifications to four existing files and the creation of two new documentation files in the `documentation/docs/Tutorial-Modules` directory.

---

## 1. Goal Description
The goal is to update the user-facing documentation of the Gruhanaksha plugin to accurately describe all features present in version 3.6.0. This includes documenting advanced sorting/preview options in the Land Parcel Numbering tool, multi-point transformations in the Aligner tool, new symbology settings in the KMZ Exporter, vertex visualization in the Polygon Splitter, and creating new, comprehensive guides for the newly added Topology Checker and Traverse Plotter tools.

---

## 2. Document Updates

### A. Modify [lpm_numbering.md](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/documentation/docs/Tutorial-Modules/lpm_numbering.md)
Update the guide to cover the new `AutoNumberDialog` configuration:
* **Custom Field**: Document the editable combobox enabling users to type or select fields other than `LP_NO`.
* **Start Corner Selection**: Detail coordinates rotation and sorting for:
  - `Top-Left`
  - `Top-Right`
  - `Bottom-Left`
  - `Bottom-Right`
* **Manual Start Feature**: Document the "Select on Canvas..." button allowing users to click a custom feature to start numbering from.
* **Flow Direction**: Document `Row-wise (Horizontal)` vs. `Column-wise (Vertical)` flow options.
* **Sorting Pattern**: Document `Serpentine (Snake)` vs. `Z-Pattern` and how they sort.
* **Algorithm Selection**: Clarify the differences between the `Smart (Adjacency)` and `Original` (strict grid) algorithms.
* **Visual Preview**: Explain how clicking "Preview" displays the sequence path and numbering on the canvas before applying.

### B. Modify [aligner.md](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/documentation/docs/Tutorial-Modules/aligner.md)
Update the guide to include all alignment operations:
* **1-Point Alignment (Move/Translate)**: Document the flow (1 source vertex + 1 target point, followed by Enter/Right-click) for simple feature movement.
* **2-Point Alignment (Scale/Align)**: Retain/update details on Scale vs. Align Only options.
* **3-Point Alignment (Affine)**: Document picking 3 source vertices and 3 target points to perform an Affine transformation (skew, rotation, scale, and translation).

### C. Modify [kmz.md](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/documentation/docs/Tutorial-Modules/kmz.md)
* **No Pin Option**: Document the "No Pin" icon option under Custom Point Symbology.
* **Categorized Symbology**: Highlight that the exporter now supports QGIS layers using Categorized styling.

### D. Modify [splitting_features.md](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/documentation/docs/Tutorial-Modules/splitting_features.md)
* **Vertex Visualization**: Document that selecting a polygon inside the Splitter Canvas now draws black circles at all its vertices to help align and snap split lines accurately.

---

## 3. New Documents

### A. New [topology_checker.md](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/documentation/docs/Tutorial-Modules/topology_checker.md)
Create a comprehensive page for the Topology Checker tool:
* **Introduction**: Explain the validation suite for polygon layers.
* **Single Layer Checks Tab**: Document all 7 rules:
  1. *Must Be Valid Geometry*: Bow-tie, self-touch, spikes, duplicate vertices.
  2. *Must Not Overlap*: Interior overlaps.
  3. *Must Not Have Gaps / Slivers*: Gaps within distance limits.
  4. *Must Not Have Duplicate Geometries*: Winding and shift-invariant canonical equality.
  5. *Must Not Be MultiPolygon*: Singlepart parcel structure check.
  6. *Micro-Polygon / Minimum Area*: Area-based filtering.
  7. *Short Edges / Spike Vertices*: Distance-based segment filtering.
* **Cross-Layer Checks Tab**: Main layer compared with other layers for gaps and overlaps.
* **Interactive Map Inspection**: Clicking errors to highlight (red outline), double-clicking to pan/zoom, green dashed previews of fixes, and the "Show Highlights" checkbox.
* **Automated Fixes**: Document sliver merging, overlap subtraction, dangling line removal, and cross-layer overlap subtraction.
* **Reports**: CSV log, HTML report, and saving the error layer.

### B. New [traverse_plotter.md](file:///c:/Users/sslr/AppData/Roaming/QGIS/QGIS3/profiles/default/python/plugins/gruhanaksha/documentation/docs/Tutorial-Modules/traverse_plotter.md)
Create a comprehensive page for the Traverse Plotter tool:
* **Overview**: Introduce plotting traverses from survey sheets.
* **Starting Parameters**: Easting, Northing, Map Canvas picking, and Initial Bearing.
* **Plotting Settings**:
  - *Angle Input Modes*: Azimuth / Bearing, Angle to Right, and Deflection Angle.
  - *Angle Formats*: Decimal Degrees vs. DD.MMSS (Surveyor DMS).
  - *Distance Units*: Gunter's Links, Meters, Feet, and Metric Links.
  - *Closed Polygon*: Connect back to start.
  - *Apply Bowditch Adjustment*: Proportional compass rule closure error distribution.
* **Traverse Table & Execution**: Adding/removing courses and plotting output memory layers (`Survey Traverse` and `Traverse Stations`).

---

## 4. Verification Plan
We will verify that the documentation builds correctly and all links/sidebar positions work as expected.
* **Documentation Build**:
  - Run the documentation compilation/builder if a local script or Docusaurus instance is present.
* **Manual Verification**:
  - Open each modified/created markdown file in the editor to ensure all formatting is correct and files are saved in the correct locations.
  - Verify that links are valid and files contain no placeholders.
