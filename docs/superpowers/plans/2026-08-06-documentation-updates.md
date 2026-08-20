# Documentation Updates for Gruhanaksha 3.6.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Update Gruhanaksha user guides for version 3.6.0.

**Architecture:** Update 4 existing markdown pages and create 2 new pages in Docusaurus tutorial module format.

**Tech Stack:** Markdown, Docusaurus

## Global Constraints
- Target directory: `documentation/docs/Tutorial-Modules/`
- Valid Docusaurus frontmatter (sidebar_position, tags, slug) must be included.
- No placeholder text (such as TODO, TBD, or similar).
- File references must use `file:///` scheme.

---

### Task 1: Update LPM Numbering Guide

**Files:**
- Modify: `documentation/docs/Tutorial-Modules/lpm_numbering.md`

- [ ] **Step 1: Edit lpm_numbering.md to add new settings**
  Update the guide to cover the new features of the `AutoNumberDialog` in detail:
  - Add details about custom Field Name selection.
  - Explain the 4 Start Corner options and coordinates rotation logic.
  - Add documentation for the "Select on Canvas..." manual start feature.
  - Document Flow Direction (Row-wise vs. Column-wise).
  - Document Sorting Pattern (Serpentine vs. Z-Pattern).
  - Document Algorithm (Smart vs. Original).
  - Document the Preview button functionality.
- [ ] **Step 2: Commit changes**
  Run:
  ```bash
  git add -f documentation/docs/Tutorial-Modules/lpm_numbering.md
  git commit -m "docs: update LPM Numbering guide to cover v3.6.0 settings"
  ```

---

### Task 2: Update Aligner Tool Guide

**Files:**
- Modify: `documentation/docs/Tutorial-Modules/aligner.md`

- [ ] **Step 1: Edit aligner.md to add 1-point and 3-point alignment**
  Update the Aligner Tool guide to document:
  - 1-Point Alignment (Move/Translate): Pick 1 source vertex and 1 target point, then press Enter or Right-click to move the feature.
  - 3-Point Alignment (Affine): Pick 3 source vertices and 3 target points to perform an Affine transformation (skew, rotation, scale, and translation).
- [ ] **Step 2: Commit changes**
  Run:
  ```bash
  git add -f documentation/docs/Tutorial-Modules/aligner.md
  git commit -m "docs: update Aligner guide to cover 1-point and 3-point alignment"
  ```

---

### Task 3: Update KMZ Exporter Guide

**Files:**
- Modify: `documentation/docs/Tutorial-Modules/kmz.md`

- [ ] **Step 1: Edit kmz.md to document No Pin and Categorized Symbology**
  Update the KMZ Exporter guide to document:
  - Under Custom Point Symbology, explain the new "No Pin" icon option.
  - Under QGIS Symbology, document that the exporter dynamically supports layers with Categorized styling.
- [ ] **Step 2: Commit changes**
  Run:
  ```bash
  git add -f documentation/docs/Tutorial-Modules/kmz.md
  git commit -m "docs: update KMZ Exporter guide to cover No Pin and Categorized Symbology"
  ```

---

### Task 4: Update Polygon Splitter Guide

**Files:**
- Modify: `documentation/docs/Tutorial-Modules/splitting_features.md`

- [ ] **Step 1: Edit splitting_features.md to document vertex markers**
  Update the Polygon Splitter guide to document:
  - Explain that when a polygon feature is selected in the Splitter Canvas, black circle vertex markers are automatically displayed on its boundaries to aid precision snapping.
- [ ] **Step 2: Commit changes**
  Run:
  ```bash
  git add -f documentation/docs/Tutorial-Modules/splitting_features.md
  git commit -m "docs: update Polygon Splitter guide to cover selected feature vertex markers"
  ```

---

### Task 5: Create Topology Checker Guide

**Files:**
- Create: `documentation/docs/Tutorial-Modules/topology_checker.md`

- [ ] **Step 1: Create topology_checker.md**
  Write a complete, beginner-friendly guide covering:
  - Overview & Purpose of validation.
  - Single Layer Checks Tab (Valid Geometry, No Overlaps, Gaps/Slivers, Duplicate Geometries, MultiPolygon checks, Micro-Polygon area, Short Edges).
  - Cross-Layer Checks Tab (Comparing Main Layer against secondary layers for gaps/overlaps).
  - Map Inspection: highlights, zooming, green dashed previews of proposed overlap fixes, and the "Show Highlights" checkbox.
  - Automated Fixes: Sliver merge, Overlap subtraction, Dangling lines removal, and Cross-Layer Overlap subtraction.
  - Reports: CSV, HTML, and memory layer exports.
- [ ] **Step 2: Commit changes**
  Run:
  ```bash
  git add -f documentation/docs/Tutorial-Modules/topology_checker.md
  git commit -m "docs: add Topology Checker guide"
  ```

---

### Task 6: Create Traverse Plotter Guide

**Files:**
- Create: `documentation/docs/Tutorial-Modules/traverse_plotter.md`

- [ ] **Step 1: Create traverse_plotter.md**
  Write a complete, detailed guide covering:
  - Overview of plotting traverses.
  - Starting Parameters (Coordinates, bearing, canvas picking).
  - Plotting Settings: Angle Modes (Azimuth, Angle to Right, Deflection Angle), Angle Formats (Decimal vs. Surveyor DD.MMSS), Distance Units (Meters, Links, Feet), Closed Polygon options, and Bowditch Compass Rule adjustment.
  - Traverse Courses Table usage.
  - Commit output memory layers (`Survey Traverse` and `Traverse Stations`) to QGIS.
- [ ] **Step 2: Commit changes**
  Run:
  ```bash
  git add -f documentation/docs/Tutorial-Modules/traverse_plotter.md
  git commit -m "docs: add Traverse Plotter guide"
  ```
