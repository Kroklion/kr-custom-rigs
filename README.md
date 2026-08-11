# Rigify Convenience & Extensions

A collection of extensions and convenience tools for Blender **Rigify**.

The project extends Rigify with a configurable eye rig, workflow tools for working with generated rigs, and optional post-processing intended to prepare Rigify output for export.

## Features

### Configurable Eye Rig

The `configurable_eye.py` module provides a custom Rigify rig type:

```text
face.configurable_eye
```

It is based on Rigify's built-in `face.skin_eye` rig and adds several configuration options.

The eye rig makes some hard-coded features of Rigify's skin_eye optional, and adds eye grouping:

* **Eye grouping** — eyes assigned to the same eye group share a controller.
* **Master control** — optionally create a master bone for moving the whole eye.
* **Iris rig** — optionally generate a dedicated iris deform/control setup.
* **Eyelid integration** — optionally connect the eye to the Rigify face eyelid system.
* **Master offset** — configure the master control position when eyelid integration is disabled.
* **Extra transforms** — optionally transfer rotation and scale from the eye target control to the eye deform bone.
* **Eye and iris deform bones** — configurable when using the eyelid-connected setup.

Rigifys `face.skin_eye` will abort the generation if not connected to eyelids. This eye rig can be used on more simple characters but still have the fancy controller.

### Driver Copy Rig

```text
basic.driver_copy
```

Extends basic.super_copy and provides these additional rig options:

* Move drivers from ORG to the DEF bone
* Replace driver parameter bones with DEF
* Add Copy Location constraint from control to DEF bone
* Add Copy Rotation constraint from control to DEF bone
* Add Copy Scale constraint from control to DEF bone

### Rigify Convenience Tools

`genrig_convenience.py` adds workflow-oriented tools to generated Rigify rigs.

The **kr Convenience Tools** panel is available in the Armature Data properties of generated Rigify rigs.

#### Weight Paint Mode

The extension provides an **Enter Weight Paint Mode / Exit Weight Paint Mode** workflow for generated Rigify rigs.

It allows the user to directly move the bones in weight paint mode (as if it were a simple armature) by conducting these steps:

1. Stores the state of the deform bone collections.
2. Stores transform locks and constraint mute states.
3. Unlocks deform bones.
4. Mutes their constraints, except constraints containing the configured keep keyword.
5. Makes the deform collections available for editing.

On exit, the previous collection visibility/solo state, transform locks and constraint states are restored, and deform bone transforms are reset.

The default constraint keep keyword is:

```text
[KEEP]
```

Constraints containing this text in their name are left enabled while entering weight-paint mode.

#### Edit Bone Widgets

**Edit Bone Widget** allows the custom widget assigned to the active pose bone to be made visible and opened directly in Edit Mode. The relevant widget collections are temporarily unhidden and their state is remembered so they can subsequently be hidden again.

#### Hide Widget Collections

**Hide Widget Collections** restores the hidden state of widget collections that were temporarily unhidden by the widget editing workflow.

#### Edit Metarig

**Edit Metarig** switches from a generated Rigify rig back to its associated metarig and enters Edit Mode. The relationship is resolved through Rigify's `rigify_target_rig` data.

#### Hide Metarig After Generation

The convenience tools can also add a **Hide Metarig After Generation** option. When enabled, the metarig is hidden by the post-generation callback.

---

## Rig Post-Processing

`postprocess.py` provides optional processing of generated Rigify rigs for export-oriented workflows.

The **kr Postprocess** panel is available on Rigify metarigs and exposes:

* **Enable kr postprocessing**
* **Root Bone**
* **Group**

The default process group is:

```text
Export
```

The group identifies the metarig bones whose corresponding deform bones should be prepared for export.
When enabled, the post-processing step can:

### Build an export bone collection

The configured metarig group is used to determine which Rigify rigs and deform bones belong in the export set. The generated armature's corresponding collection is then rebuilt around those deform bones.

### Add an export root

Optionally creates a non-deforming:

```text
DEF-root
```

bone corresponding to Rigify's `root` bone.

The generated root follows the Rigify root using location, scale and rotation constraints.

### Normalize B-Bone segments

Selected export deform bones have their B-Bone segment count reset to `1`.

### Remove stretch behavior

For the generated rig, `STRETCH_TO` constraints are disabled and replaced with `DAMPED_TRACK` constraints where applicable. IK stretch is also disabled.

### Rebuild parts of the deform hierarchy

For affected single-segment limb rigs, the base deform bone can be reparented to the corresponding deform parent. A `COPY_TRANSFORMS` constraint is then added so movement of the previous ORG parent can still be reflected where appropriate. Transform-driven deform bones are excluded from this operation.

### Rigify-specific FK handling

Single-segment `BaseLimbRig` rigs receive additional handling for FK rotation in case of only one segment.

---

## Installation
1. **Download:**  
   Download the repository as a ZIP file (Code → Download ZIP).

2. **Register with Rigify:**
   The project is intended to be installed as a Rigify extension. Edit -> Preferences -> Add-Ons -> Rigify -> Install Feature Set from File...

---

## Usage

### Configurable Eye

1. Create eye bones in a Rigify metarig.

2. Assign the custom rig type:

   ```text
   face.configurable_eye
   ```

3. Configure the eye parameters in the Rigify bone/rig settings.

4. Generate the Rigify rig.

The module also provides a sample creator that starts from Rigify's standard skin-eye sample and assigns the custom rig type.

### Driver Copy

Assign the 
```text
basic.driver_copy
```
rig to a metarig bone and configure the parameters in the Rigify bone/rig settings.


### Convenience Tools

After generating a Rigify rig, select the generated armature and open the **Armature Data Properties**.
The **kr Convenience Tools** panel provides the available workflow operators.

### Post-Processing

On the metarig:

1. Open **Armature Data Properties**.
2. Locate **kr Postprocess**.
3. Enable **Enable kr postprocessing**.
4. Add the export bone group.
5. Optionally enable the additional root bone.
6. Generate the Rigify rig.

The post-generation callback performs the configured processing automatically.

---

## Requirements

* Developed in Blender 4.4
* Rigify, as included with Blender

The code directly imports Rigify internals such as `SkinEyeRig`, `EyeClusterControl`, `BaseLimbRig`, Rigify generator functionality, and Rigify naming/utilities.
Because these are internal Rigify APIs rather than a stable external interface, compatibility may depend on the Blender version.

---

## Design Notes

The extension deliberately builds on Rigify rather than replacing its generation system.

The configurable eye rig subclasses Rigify's existing `SkinEyeRig`, while the other modules register post-generation callbacks through the project's hook mechanism.
This means the project is closely coupled to Rigify's generated rig structure and naming conventions, including `ORG-`, `DEF-`, `MCH-` and Rigify-specific metadata.

In particular, the post-processing code assumes the presence of Rigify deform bones and generator information when determining which bones belong to the configured export group.

---

## Limitations

Potential compatibility issues include:

* Makes use of Bone Collections, so Blender 4.0+.
* Changes to Rigify's internal Python code (pre/post generation hooks).
* Changes to generated hierarchy.
* Differences in Rigify behavior between Blender versions.
* Export pipelines with requirements different from those assumed by the post-processing code.

Always test generated rigs and exported animation in the target application.

---

## License

This project is licensed under the terms of the [GNU General Public License v3.0](LICENSE).

---

## Contributing

This project is primarily developed for personal Blender workflows.  
I don’t intend to run a full open‑source project around it, so my time for maintenance will be limited.  
That said, I’m open to **ideas, suggestions, or small contributions** if they align with the goals of the extension.  
Please understand that responses to issues or pull requests may be slow.

---

## Acknowledgements

This project extends and builds upon Blender's **Rigify** system, particularly its face and limb rig implementations.
