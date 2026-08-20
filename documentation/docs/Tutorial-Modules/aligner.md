---
sidebar_position: 9
keywords:
  - align
  - transform
  - scale
  - rotate
  - georeference
  - affine
  - gruhanaksha
tags: [aligner, transform, georeferencing, affine]
slug: aligner
---

# 🛠️ Aligner Tool

`Available from v2.1.0`

This powerful tool allows you to **align, rotate, scale, and skew** vector features (lines or polygons) with precision. It works by mapping "source" vertices on your feature to corresponding "target" destination points on the map, supporting 1-point, 2-point, and 3-point transformations.

## ✅ Prerequisites

- An editable **Line or Polygon layer** must be the active layer in QGIS.
- The layer must be in **editing mode** (pencil icon ✏️ activated).
- For best results, **enable snapping** in `Project > Snapping Options...` to accurately select vertices and target coordinates.

---

## 🔄 Modes of Alignment

Depending on the number of control point pairs you select, the tool performs different geometric operations:

### 1. One-Point Alignment (Translation / Move)
* **What it does**: Moves the entire feature to a new location without rotating or resizing it.
* **How to use**: 
  1. Pick **one target point** on the map.
  2. Pick the **corresponding source vertex** on your feature.
  3. Press **Enter** (or right-click) to complete the move.

### 2. Two-Point Alignment (Translate, Rotate & Optional Scale)
* **What it does**: Moves and rotates the feature to align with a baseline. You can choose whether to scale it.
* **How to use**:
  1. Select the **first target point** and **first source vertex**.
  2. Select the **second target point** and **second source vertex**.
  3. A dialog box will appear asking you to choose:
     - **Scale**: Moves, rotates, and scales the feature so that the baseline matches the target distance exactly.
     - **Align Only**: Moves and rotates the feature while keeping its original size and shape.

### 3. Three-Point Alignment (Affine Transformation)
* **What it does**: Moves, rotates, scales, and skews/shears the feature. Ideal for fitting complex features into coordinates where skewing is necessary.
* **How to use**:
  1. Select the **first target point** and **first source vertex**.
  2. Select the **second target point** and **second source vertex**.
  3. Select the **third target point** and **third source vertex**.
  4. The transformation will be calculated and applied automatically using a 3-point Affine algorithm.

---

## 🧭 Step-by-Step Instructions (Example: 2-Point Alignment)

### 🟩 Step 1: Activate the Tool
1. Make sure your desired line or polygon layer is **active** and in **editing mode**.
2. Click the **Aligner Tool** icon from the plugin toolbar or menu.
3. The message bar will prompt: 
   > "Tool activated on layer '<Layer Name>'. Left-click to pick points, right-click to reset."

### 🟩 Step 2: Select the First Pair of Points
1. **Select Target Point 1**: Left-click on the map where you want the first vertex to end up. A red marker will appear.
2. **Select Source Vertex 1**: Left-click on the vertex of the feature you want to move. A blue dashed line will connect the target point and source vertex.

### 🟩 Step 3: Select the Second Pair of Points
1. **Select Target Point 2**: Left-click on the map to define the second destination. A second red marker will appear.
2. **Select Source Vertex 2**: Left-click on the second vertex on your feature. A second blue dashed line will appear.

### 🟩 Step 4: Perform the Transformation
* **For 1-Point or 2-Point Alignment**: If you have finished picking your control points (e.g., 2 pairs), press **Enter** (or right-click) to execute the alignment.
* **For 3-Point Alignment**: Proceed to click the third target point and third source vertex. The alignment executes immediately upon the 6th click (3rd pair).

---

## 💡 Tips and Additional Features

- **Multi-Feature Alignment**: If you select multiple features in the active layer *before* activating the tool, the calculated transformation is applied to all of them together.
- **Resetting**: A **right-click** at any time before the execution will cancel the current selection and reset the tool to step 0.
- **Visual Feedback**:
  - **Red Points**: Show your target destination locations.
  - **Blue Dashed Lines**: Show the mapping from your source vertices to target points.
  - **Magenta Cross**: QGIS Snap indicator showing when you are successfully snapped to a vertex or edge.

## 🛑 To Exit the Tool
Simply select any other tool from the QGIS toolbars (like the Pan or Select tool). The Aligner Tool will automatically deactivate.
