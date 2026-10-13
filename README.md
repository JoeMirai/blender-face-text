# Blender Face Text

Engrave or emboss text such as `123` onto one selected flat mesh face, with text height and depth entered in **millimeters**.

- Text height is the **actual visible height of the complete text**, rather than the font's nominal em size. For multiline text this is the total block height.
- Engrave inward or emboss outward by an exact depth relative to the face plane.
- Center on the face, with horizontal/vertical offsets in mm and rotation in degrees.
- Optional TTF/OTF font file; Blender's built-in font is the default.
- Reads the scene's unit scale correctly, including Metric scenes with scale `0.001`.
- Handles rotated and nonuniformly scaled objects without applying their transforms.
- Creates a live Exact Boolean and hidden mesh helper; supports Undo and Remove Last Face Text.

## Quick install from Blender's Python Console

In Blender press **Shift+F4**, paste the following block, and press Enter. It downloads the add-on from this repository, enables it, and saves your preferences so it loads next time. Internet access is required.

```python
import bpy, urllib.request, pathlib, addon_utils, importlib, sys
p = pathlib.Path(bpy.utils.user_resource('SCRIPTS', path='addons', create=True)) / 'face_text.py'
p.write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/JoeMirai/blender-face-text/main/face_text.py', timeout=30).read())
addon_utils.disable('face_text', default_set=False)
importlib.invalidate_caches(); sys.modules.pop('face_text', None)
addon_utils.enable('face_text', default_set=True, persistent=True); bpy.ops.wm.save_userpref()
```

For console paste convenience, the same installation is available as one command:

```python
exec("import bpy, urllib.request, pathlib, addon_utils, importlib, sys\np = pathlib.Path(bpy.utils.user_resource('SCRIPTS', path='addons', create=True)) / 'face_text.py'\np.write_bytes(urllib.request.urlopen('https://raw.githubusercontent.com/JoeMirai/blender-face-text/main/face_text.py', timeout=30).read())\naddon_utils.disable('face_text', default_set=False)\nimportlib.invalidate_caches(); sys.modules.pop('face_text', None)\naddon_utils.enable('face_text', default_set=True, persistent=True)\nbpy.ops.wm.save_userpref()")
```

Alternatively download `face_text.py`, use Preferences > Add-ons > Install from Disk, and enable Face Text.

## Use

1. Return to the 3D View with **Shift+F5**. Select your mesh and enter **Edit Mode** with Tab.
2. Use face selection and select **exactly one flat face**. Edit only one object at a time.
3. Press **N** and open the **Face Text** sidebar tab.
4. Enter your text, **Text height (mm)**, **Depth (mm)**, and choose **Engrave (in)** or **Emboss (out)**.
5. Adjust offsets, rotation, or font as needed, then click **Create Face Text**.
6. The add-on returns to Object Mode to show the Boolean result. Save your `.blend`.

Settings apply to the **next** text operation. To revise a result, choose **Remove Last Face Text**, select the face again, and create it with the new settings. Multiple text operations can be stacked.

## Notes

Use a closed solid with outward-facing normals for reliable printable results. Engraving depth should be less than the solid's thickness unless you intend a through-cut. Text is centered on the face's vertex average, with horizontal direction derived from the object's local X axis (local Y fallback); rotation lets you choose its orientation.

The text is not automatically resized or clipped to the face: its entered height stays exact. Choose a height and offsets that keep it within the face. The selected face must be flat; this does not wrap text over curved surfaces. Place text before modifiers that substantially change the selected face's position, or apply those modifiers first. Live Booleans are appended to the modifier stack.

The helper is hidden in the viewport and renders but remains available to the Boolean. It is parented to your object and moves with it. Applying the Boolean bakes the geometry; the hidden helper may then be deleted manually. Fonts are converted to meshes at creation, so recipients of your `.blend` do not need the font file.

Targets Blender 4.2 and newer; **tested on Blender 5.2.0**.

## Test

```sh
blender --background --factory-startup --python tests/test_blender.py
```

Tests exercise engraving and embossing, actual height/depth, resulting solid volume, millimeter conversion, rotation/nonuniform scale, helper removal, invalid selection, and registration lifecycle.

## License

GPL-3.0-or-later.
