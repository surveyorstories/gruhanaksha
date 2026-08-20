---
sidebar_position: 14
slug: splittingfeatures
---

# ✂️ Polygon Splitter

`Available from v3.0.0`

:::info
This tool is built upon the **[Split Features On Steroids](https://plugins.qgis.org/plugins/SplitPolygonShowingAreas/)** plugin, featuring enhancements and adaptations tailored to Resurvey requirements.
:::

The **Polygon Splitter** provides a dedicated interactive environment for precisely dividing polygon features. It opens a custom window with a map canvas where you can draw split lines, edit vertices, automatically adjust areas to target values, and add measurement markers.

---

## 🚀 Getting Started

### Launching the Tool

1. Load a polygon layer in QGIS.
2. Select the polygon layer in the Layers panel.
3. Click the **Polygon Splitter** icon from the Gruhanaksha plugin menu.
4. A new window titled "Gruhanaksha Polygon Splitter" will open.

### Interface Overview

The Polygon Splitter window contains:

- **Map Canvas**: Displays your selected layers and features. This mirrors the main QGIS canvas.
- **Toolbar**: Contains all editing and measurement tools (detailed below).
- **Unit Selector**: Dropdown menu to choose measurement units for areas and lengths.
  - **Area Units**: Acres, Hectares, Sq Meters, Sq Feet, Sq Yards, **Guntas**
  - Linear units are automatically paired with area units (e.g., feet with acres)
- **Layer Selection Button**: Choose which layers to display in the splitter canvas.

### Changing Measurement Units

The **Unit Selector** dropdown is located in the toolbar and allows you to change how areas and lengths are displayed.

**How to Use**:

1. Click the **Unit Selector** dropdown in the toolbar.
2. Choose your preferred unit from the list:
   - **Acres** (with feet for linear measurements)
   - **Hectares** (with meters for linear measurements)
   - **Sq Meters** (with meters for linear measurements)
   - **Sq Feet** (with feet for linear measurements)
   - **Sq Yards** (with yards for linear measurements)
   - **Guntas** (with feet for linear measurements)
3. All area and length labels will immediately update to show values in the selected unit.
4. The unit change applies to:
   - Real-time area calculations during splitting
   - Segment length labels
   - The "Adjust Area" tool target values
   - Marker distance measurements

---

## 🛠️ Toolbar Tools - Detailed Guide

| ![arrow](../img/canvas_one/arrow.svg) | **Select Features** |
|---|---|

**Purpose**: Select polygon features to split.

**How to Use**:

1. Click the **Select Features** button (this is the default tool).
2. Click on any polygon in the canvas to select it.
3. Selected features will be highlighted in yellow, and all their vertices will be marked with **black circular indicators**.
   - *These vertex markers make it easy to see the exact vertices of the polygon and snap your split line directly to them for precision cuts.*
4. Hold **Ctrl** to select multiple polygons.

| ![cut](../img/canvas_one/cut.svg) | **Start Splitting** |
|---|---|

**Purpose**: Draw a line across the polygon to define where it will be split.

**How to Use**:

1. Click the **Start Splitting** button.
2. Click on the map to place the first point of your split line.
3. Continue clicking to add more points along the desired split path.
4. As you draw, you'll see:
   - A **red solid line** showing the drawn portion
   - A **red dotted line** previewing the next segment
   - **Area labels** showing the size of each resulting part
   - **Length labels** on new segments created by the split
5. **Right-click** or press **Enter** to finish drawing the line.
6. The split will be performed immediately.

| ![movevertex](../img/canvas_one/movevertex.svg) | **Move Vertices** |
|---|---|

**Purpose**: Adjust the position of individual points on the split line.

**How to Use**:

1. Draw a split line first (don't finish it yet).
2. Click the **Move Vertices** button.
3. Click and drag any vertex (point) on the split line to a new position.
4. The line will update in real-time, showing new area calculations.
5. Vertices snap to nearby features if snapping is enabled.
6. **Right-click** when done to perform the split.

| ![addvertex](../img/canvas_one/addvertex.svg) | **Add Vertices** |
|---|---|

**Purpose**: Insert new points along the split line for more control.

**How to Use**:

1. Draw a split line with at least 2 points.
2. Click the **Add Vertices** button.
3. Click on any **segment** (line between two points) where you want to add a new vertex.
4. A new point will be inserted at that location.
5. You can add multiple vertices.
6. **Right-click** when done to perform the split.

| ![removevertex](../img/canvas_one/removevertex.svg) | **Remove Vertices** |
|---|---|

**Purpose**: Delete unnecessary points from the split line.

**How to Use**:

1. Draw a split line with at least 3 points.
2. Click the **Remove Vertices** button.
3. Click on any **vertex** (point) you want to remove.
4. The vertex will be deleted and the line will reconnect.
5. You cannot remove vertices if only 2 points remain.
6. **Right-click** when done to perform the split.

| ![movesegment](../img/canvas_one/movesegment.svg) | **Move Segment** |
|---|---|

**Purpose**: Shift an entire segment (line between two points) while keeping it parallel to its original direction.

**How to Use**:

1. Draw a split line with at least 3 points.
2. Click the **Move Segment** button.
3. Click and drag on a **segment** (not a vertex).
4. The segment will move parallel to itself, adjusting the adjacent vertices.
5. Useful for fine-tuning the split position without changing the angle.
6. **Right-click** when done to perform the split.

| ![line_close](../img/canvas_one/line_close.svg) | **Close Line** |
|---|---|

**Purpose**: Connect or disconnect the start and end points of the split line to create a closed loop.

**How to Use**:

- **Close Line**
  1. Draw a split line with at least 3 points.
  2. Click **Close Line**.
  3. The last point will connect to the first point, creating a closed polygon.
  4. Useful for creating enclosed areas within a polygon.

| ![line_open](../img/canvas_one/line_open.svg) | **Open Line** |
|---|---|

- **Open Line**
  1. If you have a closed line, click **Open Line**.
  2. The connection between start and end will be removed.

| ![moveline](../img/canvas_one/moveline.svg) | **Move Line** |
|---|---|

**Purpose**: Shift the entire split line to a new position without changing its shape.

**How to Use**:

1. Draw a split line.
2. Click the **Move Line** button.
3. Click and drag anywhere on the canvas.
4. The entire line will move parallel to the drag direction.
5. All vertices maintain their relative positions.
6. **Right-click** when done to perform the split.

|  | **Adjust Area** |
|---|---|

**Purpose**: Automatically adjust the split line to achieve a specific target area for one of the resulting parts.

**How to Use**:

1. Draw a split line across the polygon.
2. Click the **Adjust Area** button.
3. A dialog will appear showing the current areas of each part.
4. **Select the part** you want to adjust (e.g., "Part 1").
5. **Enter the target area** value (e.g., "20" for 20 Guntas).
6. Ensure the **Unit Selector** in the toolbar shows the correct unit.
7. Click **Adjust**.
8. The tool will automatically shift the split line perpendicular to its direction to match the target area.
9. The algorithm uses iterative calculations to find the exact position.

**Note**: If the target area is impossible (e.g., larger than the total polygon area), the adjustment will fail with a warning.

|  | **Add Marker** |
|---|---|

**Purpose**: Place temporary reference markers on the canvas to verify distances and measurements.

**How to Use**:

1. Click the **Add Marker** button.
2. Click anywhere on the map to place a red square marker.
3. The marker will snap to the nearest polygon boundary.
4. As you move the mouse, you'll see distance labels showing:
   - Distance from the marker to the start of the boundary segment
   - Distance from the marker to the end of the boundary segment
5. Place multiple markers to create reference points.

**Editing Markers**:

1. **Right-click** on an existing marker.
2. The **Edit Marker Distance** dialog will open.
3. You can:
   - **Adjust Distance**: Type an exact distance value (e.g., "15.5") to move the marker along the boundary segment.
   - The two input fields show "Distance from Start" and "Distance from End" - they update automatically as you type.
   - **Delete Marker**: Click the "Delete Marker" button to remove it.

**Note**: Markers are visual guides only and do not affect the split operation.

| ![snap](../img/canvas_one/snap.svg) | **Snap Toggle** |
|---|---|

**Purpose**: Enable or disable snapping to existing features.

**How to Use**:

1. Click the **Snap Toggle** button to turn snapping on or off.
2. When enabled (button appears pressed), vertices and markers will snap to:
   - Existing polygon vertices
   - Polygon edges
   - Other features in the canvas
3. Configure snapping settings in the main QGIS window for more control.

---

## 📝 Basic Workflow

Here's the typical process for splitting a polygon:

1. **Select Layers**: Click "Select Layers" to choose which layers to display.
2. **Select Feature**: Click on a polygon to select it (it will highlight in yellow).
3. **Draw Split Line**:
   - Click "Start Splitting"
   - Click points to draw the line across the polygon
   - Watch the area labels update in real-time
4. **Refine (Optional)**:
   - Use Move/Add/Remove Vertices to perfect the line
   - Use "Adjust Area" if you need an exact area value
5. **Perform Split**:
   - Right-click or press Enter
   - The polygon will be split into separate features
6. **Save**: Save your edits in the main QGIS window (Ctrl+S).

---

## ⌨️ Keyboard Shortcuts

| Shortcut | Action |
| --- | --- |
| **Ctrl + Z** | Undo last action |
| **Ctrl + Y** | Redo last undone action |
| **Esc** | Stop current operation / Cancel tool |
| **Enter** | Finish drawing split line |
| **Right-Click** | Finish drawing line OR Perform split |
| **Backspace** or **Delete** | Remove last vertex while drawing |

---

## 💡 Best Practices

### Snapping Configuration

- Configure snapping settings in QGIS before starting (Settings → Snapping Options).
- Set an appropriate snapping tolerance (e.g., 10 pixels).
- Enable snapping to vertices and segments for precision.
- Use the Snap Toggle in the toolbar to quickly enable/disable snapping.

### Layer Management

- Use the "Select Layers" button to show only relevant layers in the splitter window.
- Lock layers you don't want to edit accidentally.
- Temporarily hide layers to reduce visual clutter.

### Working with Complex Splits

- For complex geometries, work incrementally - split in stages rather than all at once.
- Use the "Add Marker" tool to verify measurements before finalizing splits.
- Use "Adjust Area" for precise land parcel divisions where exact areas are required.
- Save frequently to prevent data loss.

### Undo/Redo

- Use Ctrl+Z to undo mistakes immediately.
- The undo/redo functionality works for both drawing operations and completed splits.
- Undo history is maintained even after performing a split.

---

## 🌍 Common Use Cases

- **Land Parcel Division**: Divide large parcels into smaller plots with exact area requirements.
- **Boundary Adjustments**: Correct or modify existing polygon boundaries.
- **Resurvey Operations**: Split parcels according to survey measurements using markers for verification.
- **Property Subdivision**: Create new property boundaries with precise area calculations.

---

## 🎉 Conclusion

The Polygon Splitter tool provides a powerful, interactive environment for precise polygon division. With real-time area calculations, automatic area adjustment, and comprehensive editing tools, it streamlines complex splitting operations while maintaining accuracy. Whether you're dividing land parcels, adjusting boundaries, or performing detailed resurvey work, this tool offers the flexibility and precision needed for professional GIS editing.
