---
sidebar_position: 16
slug: lpnumbering
---

# 📌Land Parcel Numbering Tool

`Available from v3.0.0`

:::info
This tool provides comprehensive functionality for interactively numbering land parcels in QGIS. It combines manual control with powerful auto-numbering algorithms designed for different parcel layouts.
:::

## 🌟 Key Features

- **Advanced Auto-Numbering Dialog**: Configure custom fields, start corners, custom start features, flow directions, sorting patterns, and algorithms.
- **Interactive Visual Preview**: Visualize the proposed numbering path and sequence numbers on the map canvas before committing.
- **Intelligent Manual Numbering**: Click-to-assign with automatic duplicate detection and smart sequence tracking.
- **Edit Mode Auto-Detection**: Automatically handles layer locking/unlocking.
- **Data Integrity**: Built-in safeguards against accidental data overwrites.
- **Visual Feedback**: Color-coded symbology to instantly see status (Duplicates, Edited, Auto-numbered).

---

## 🛠️ The Toolbar Interface

The toolbar is vertically split into **Map Tools** (Left) and **Data Tools** (Right).

### Map Tools (Left Side)

Use these for navigation and numbering operations.

1. **Zoom In / Out**: Standard map navigation.
2. **Pan**: Click and drag to move the map.
3. **Smart Select**: Draw a rectangle to select a subset of parcels. Only selected parcels will be auto-numbered.
4. **Deselect**: Clear the current selection.
5. **Auto Number Settings (Gear/Snake Icons)**: Opens the advanced Auto Number Settings dialog.
6. **Manual Numbering (Crosshair)**: Point-and-click numbering tool.

### Data Tools (Right Side)

Use these to manage the underlying database.

1. **Open Attribute Table**: Opens the standard QGIS attribute table for the layer.
2. **Delete Label Field (Trash Icon)**: Opens a multi-select dialog to delete fields (e.g., to clear `LP_NO` and start fresh).

---

## ⚙️ Advanced Auto-Numbering Dialog Settings

When you launch the Auto Number tool, a dialog with the following settings will appear:

* **Field Name**: An editable combobox where you can select an existing attribute field (defaults to `LP_NO`) or type a new field name to create it.
* **Start Number**: A numeric input indicating the starting sequence number. The tool automatically detects and defaults to `last max value + 1` or `1` if empty.
* **Start Corner**: Choose which quadrant of the target area to begin numbering from:
  - **Top-Left (NW)**
  - **Top-Right (NE)**
  - **Bottom-Left (SW)**
  - **Bottom-Right (SE)**
* **Manual Start (Selected Start)**: Click the **"Select on Canvas..."** button and click directly on a parcel in the QGIS canvas. The numbering sequence will begin exactly at this parcel, overriding the default mathematical corner.
* **Flow Direction**:
  - **Row-wise (Horizontal)**: Groups features into horizontal rows and numbers them along the X-axis.
  - **Column-wise (Vertical)**: Groups features into vertical columns and numbers them along the Y-axis.
* **Pattern**:
  - **Serpentine (Snake)**: Reverses the sequence direction on every alternate row or column, creating a continuous winding flow.
  - **Z-Pattern**: Numbers each row/column in the same direction, resetting back to the start side for the next row/column.
* **Algorithm**:
  - **Smart (Adjacency)**: Guided by adjacency checks. It traverses greedily to adjacent features sharing a boundary, prioritizing local neighbors and larger shared boundaries. Ideal for irregular or curved parcel layouts.
  - **Original (Strict Grid)**: Follows the coordinates and sorting pattern strictly. Recommended for clean grid/checkerboard layouts.

---

## 🧬 Spatial Sorting & Adjacency Logic

To handle tilted grids and irregular parcels, the "Smart" auto-numbering algorithm runs the following steps under the hood:
1. **Dominant Angle Detection**: Analyzes segment orientations to compute the dominant angle.
2. **Coordinate Rotation**: Rotates the coordinates of the feature centroids by the dominant angle to align the grid axes.
3. **Row/Column Grouping**: Groups centroids into rows or columns using a spatial tolerance (e.g., `0.75 * avg_height` for rows) before sorting.
4. **Adjacency Guided Traversal**: Traverses features starting from Rank 0, jumping to the neighbor with the largest shared boundary to keep numbering contiguous.

---

## 👁️ Visual Numbering Preview

Before applying the numbering to your database:
1. Click the **"Preview"** button in the dialog.
2. A green dashed path line (`QgsRubberBand`) will appear on the canvas connecting the centroids of the parcels in the calculated sequence.
3. Sequence numbers will be rendered on the map canvas as a temporary layer so you can inspect the flow.
4. Change settings (e.g., swap start corner or pattern) and click **"Preview"** again to see the updated path instantly.
5. Click **"OK"** to write the numbers to the attribute field and clear the preview, or click **"Cancel"** to discard.

---

## 📖 Step-by-Step Usage

### Auto-Numbering Workflow

1. **Select (Optional)**: Use the **Smart Select** tool to highlight a block of parcels. If nothing is selected, the entire layer is processed.
2. **Open Settings**: Click the Auto Number icon to open the settings dialog.
3. **Configure**: Select the target field, start number, corner, flow direction, pattern, and algorithm.
4. **Preview**: Click **Preview** to visually verify the path on your map canvas.
5. **Apply**: Click **OK** to write the numbers.

### Manual Numbering Workflow

1. Click the **Manual Numbering (Crosshair)** tool.
2. **Basic Assignment**: Left-click on a parcel to assign the current sequence number.
3. **Advanced Swiping (Drag to Label)**:
     - **Right Click + Drag**: Draw a line across multiple parcels. Any parcel the line touches will be numbered in sequence instantly.
     - **Ctrl + Left Click + Drag**: Alternative way to draw a numbering line.
4. **Editing**: Hold **Alt + Click** on a parcel to edit its existing number.
5. **Duplicates**: If you assign a duplicate number, the tool will warn you and highlight duplicates in **Red**.

---

## 🎨 Symbology & Status Codes

The tool automatically applies a rule-based style to help you visualize progress.

| Color | Status | Meaning |
| :--- | :--- | :--- |
| **Green** 🟢 | `Unique` | Valid, unique number. |
| **Red** 🔴 | `Duplicate` | This number exists on multiple parcels. |
| **Yellow** 🟡 | `Edited` | Manually changed by user (tracked for quality control). |
| **Blue** 🔵 | `Cleared` | Was a duplicate, but you fixed/cleared it. |
| **Gray** ⚪ | `Null` | Unnumbered parcel. |

*Note: The tool tracks these states in a hidden `STATUS` field (`auto`, `manual_edit`, `duplicate`, etc.) for your reference.*

---

## ⚡ Power User Tips

- **Clean Slate**: To completely restart, use the **Delete Label Field** (Trash Can) to delete the `LP_NO` field.
- **Keyboard Shortcuts**:
  - **Ctrl + Z**: Undo the last manual action.
  - **Ctrl + Y**: Redo.
  - **Alt + Click**: Edit a specific label.
- **Performance**: For layers with 10,000+ parcels, **Select** a smaller area before auto-numbering. Processing the entire layer at once may take a few seconds.

---

## ❓ Troubleshooting

**"Layer is not in edit mode"**
- The tool now handles this! Just click "Yes" when prompted to start editing.

**"My numbers are jumping across the street!"**
- Try the **Smart (Adjacency)** algorithm. It is better at detecting "local neighbors" than the strict grid algorithm. Also verify that you have chosen the correct flow direction (Row-wise vs Column-wise) matching the road layout.

**"I can't see the labels!"**
- Click the **Refresh** button in QGIS or toggle visibility. Ensure the specified field exists (use the Attribute Table button to check).
