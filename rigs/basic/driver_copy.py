import bpy
from rigify.rigs.basic.super_copy import Rig as SuperCopyRig
from rigify.utils.layers import ORG_COLLECTION
from rigify.utils.layers import DEF_COLLECTION


class Rig(SuperCopyRig):
    def rig_bones(self):
        super().rig_bones()

        org = self.bones.org
        def_bone = self.bones.deform

        params = self.params

        if params.move_drivers_to_def or params.drive_from_def:
            self._process_org_drivers(org, def_bone, params)
            
        # ---------------------------------------------------------
        # Add constraints to DEF bone if requested
        # ---------------------------------------------------------
        if params.make_control:
            pbone = self.obj.pose.bones[def_bone]

            if params.copy_loc_from_org:
                con = pbone.constraints.new('COPY_LOCATION')
                con.name = "Copy Location from ORG"
                con.target = self.obj
                con.subtarget = org

            if params.copy_rot_from_org:
                con = pbone.constraints.new('COPY_ROTATION')
                con.name = "Copy Rotation from ORG"
                con.target = self.obj
                con.subtarget = org

            if params.copy_scale_from_org:
                con = pbone.constraints.new('COPY_SCALE')
                con.name = "Copy Scale from ORG"
                con.target = self.obj
                con.subtarget = org

    # -------------------------------------------------------------------------
    # DRIVER PROCESSING (ORG ONLY)
    # -------------------------------------------------------------------------

    def _process_org_drivers(self, org, def_bone, params):
        """Process only drivers that live on the ORG bone."""

        obj = self.obj
        ad = obj.animation_data
        if not ad or not ad.drivers:
            return

        # Drivers on ORG bone always have data_paths containing:
        #   pose.bones["ORG-xxx"]
        #   pose.bones["ORG-pelvis.L.001"].rotation_quaternion
        org_path = f'pose.bones["{org}"]'

        # Collect first to avoid modifying while iterating
        org_drivers = [
            fcurve for fcurve in ad.drivers
            if org_path in fcurve.data_path
        ]
        
        for fcurve in org_drivers:
            drv = fcurve.driver
            
            # 1) Rewrite driver variables to reference DEF bone (before moving them away)
            if params.drive_from_def:
                self._rewrite_driver_variables(drv)

            # 2) Move the driver to DEF bone
            if params.move_drivers_to_def:
                self._relocate_driver_to_def(obj, fcurve, org, def_bone)


    # -------------------------------------------------------------------------
    # MOVE DRIVER
    # -------------------------------------------------------------------------

    def _relocate_driver_to_def(self, obj, fcurve, org, def_bone):
        """Move the driver from ORG to DEF bone and copy all variable settings."""

        old_path = fcurve.data_path
        new_path = old_path.replace(
            f'pose.bones["{org}"]',
            f'pose.bones["{def_bone}"]'
        )
        
        # Rotation modes of bones must match
        org_pbone = obj.pose.bones.get(org)
        def_pbone = obj.pose.bones.get(def_bone)

        if org_pbone and def_pbone:
            # Copy rotation mode from ORG to DEF
            def_pbone.rotation_mode = org_pbone.rotation_mode

        # Create new driver
        new_fcurve = obj.driver_add(new_path, fcurve.array_index)
        new_driver = new_fcurve.driver
        old_driver = fcurve.driver

        # Copy basic driver settings
        new_driver.type = old_driver.type
        new_driver.expression = old_driver.expression

        # Remove default variables Blender adds
        while new_driver.variables:
            new_driver.variables.remove(new_driver.variables[0])

        # Copy variables from old driver
        for var in old_driver.variables:
            new_var = new_driver.variables.new()
            new_var.name = var.name
            new_var.type = var.type

            # Copy all targets (not just the first)
            for i, src_tgt in enumerate(var.targets):
                # Blender ensures the target slot exists
                tgt = new_var.targets[i]

                # Copy ID (armature object)
                tgt.id = src_tgt.id

                # Copy bone target
                tgt.bone_target = src_tgt.bone_target

                # Copy data path
                tgt.data_path = src_tgt.data_path

                # Copy transform‑related settings
                tgt.transform_type = src_tgt.transform_type
                tgt.transform_space = src_tgt.transform_space

                # Copy fallback settings
                tgt.use_fallback_value = src_tgt.use_fallback_value
                tgt.fallback_value = src_tgt.fallback_value

                # Copy rotation mode (Euler/Quat/Axis‑Angle)
                tgt.rotation_mode = src_tgt.rotation_mode

        # Remove old driver
        obj.driver_remove(old_path, fcurve.array_index)


    # -------------------------------------------------------------------------
    # REWRITE VARIABLES
    # -------------------------------------------------------------------------

    def _rewrite_driver_variables(self, driver):
        """Rewrite driver variable bone targets to DEF bone."""
        for var in driver.variables:
            for tgt in var.targets:
                if tgt.id == self.obj and tgt.bone_target:
                    if tgt.bone_target.startswith(ORG_COLLECTION + '-'):
                        suffix = tgt.bone_target[len(ORG_COLLECTION):]
                        new_name = DEF_COLLECTION + suffix
                        tgt.bone_target = new_name


    # -------------------------------------------------------------------------
    # PARAMETERS
    # -------------------------------------------------------------------------

    @classmethod
    def add_parameters(cls, params):
        """ Add the parameters of this rig type to the
                RigifyParameters PropertyGroup
        """
        params.move_drivers_to_def = bpy.props.BoolProperty(
            name="Drivers to DEF bones",
            default=True,
            description="Move drivers from ORG to the DEF bone"
        )
        
        params.drive_from_def = bpy.props.BoolProperty(
            name="Replace driver targets",
            default=True,
            description="Replace driver parameter bones with DEF"
        )
        
        # (only meaningful when make_control is True)
        params.copy_loc_from_org = bpy.props.BoolProperty(
            name="Copy Location from ORG",
            default=False,
            description="Add Copy Location constraint to DEF bone"
        )

        params.copy_rot_from_org = bpy.props.BoolProperty(
            name="Copy Rotation from ORG",
            default=False,
            description="Add Copy Rotation constraint to DEF bone"
        )

        params.copy_scale_from_org = bpy.props.BoolProperty(
            name="Copy Scale from ORG",
            default=False,
            description="Add Copy Scale constraint to DEF bone"
        )
        
        super().add_parameters(params)
        
    @classmethod
    def parameters_ui(cls, layout, params):
        super().parameters_ui(layout, params)
        
        layout.prop(params, "move_drivers_to_def")
        layout.prop(params, "drive_from_def")
        
        if params.make_control:
            box = layout.box()
            box.label(text="Constraints on DEF from ORG:")
            box.prop(params, "copy_loc_from_org")
            box.prop(params, "copy_rot_from_org")
            box.prop(params, "copy_scale_from_org")

