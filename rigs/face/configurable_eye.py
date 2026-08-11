import bpy
from rigify.rigs.face.skin_eye import Rig as SkinEyeRig
from rigify.rigs.face.skin_eye import EyeClusterControl
from rigify.rigs.face.skin_eye import create_sample as skin_eye_sample
from rigify.base_rig import stage
from mathutils import Vector, Matrix
from rigify.utils.naming import make_derived_name
from rigify.utils.widgets_basic import create_circle_widget
from rigify.utils.bones import put_bone
from rigify.rig_ui_template import PanelLayout
from rigify.generate import WGT_PREFIX


class Rig(SkinEyeRig):
    # UTILS
    def create_cluster_control(self):
        return MultipleEyeClusterControl(self)

    def get_master_control_position(self) -> Vector:
        if self.params.connect_eyelids:
            return super().get_master_control_position()
        else:
            return self.center + self.axis * self.params.master_offset
    
    ####################################################
    # SCRIPT

    @stage.configure_bones
    def configure_script_panels(self):
        if self.params.connect_eyelids:
            super().configure_script_panels()
            
    def add_ui_sliders(self, panel: PanelLayout, *, add_name=False):
        if self.params.connect_eyelids:
            super().add_ui_sliders(panel, add_name=add_name)
            
    ####################################################
    # Master control

    @stage.generate_bones
    def make_master_control(self):
        if self.params.create_master_rig:
            super().make_master_control()

    @stage.configure_bones
    def configure_master_control(self):
        if self.params.create_master_rig:
            super().configure_master_control()

    @stage.generate_widgets
    def make_master_control_widget(self):
        if self.params.create_master_rig:
            ctrl = self.bones.ctrl.master
            if self.params.connect_eyelids:
                create_circle_widget(self.obj, ctrl, radius=1, head_tail=0.25)
            else:
                create_circle_widget(self.obj, ctrl, radius=1, head_tail=0)
    
    ####################################################
    # Tracking MCH
    
    @stage.generate_bones
    def make_mch_track_bones(self):
        if self.params.connect_eyelids:
            super().make_mch_track_bones()
        else:
            # only looking direction bone needed
            org = self.bones.org
            mch = self.bones.mch

            mch.master = self.copy_bone(org, make_derived_name(org, 'mch'))
            

    @stage.parent_bones
    def parent_mch_track_bones(self):
        if self.params.create_master_rig:
            super().parent_mch_track_bones()
        else:
            mch = self.bones.mch
            parent = self.bones.org
            self.set_bone_parent(mch.master, parent)

            
    @stage.rig_bones
    def rig_mch_track_bones(self):
        if self.params.connect_eyelids:
            super().rig_mch_track_bones()
        else:
            mch = self.bones.mch
            ctrl = self.bones.ctrl

            # Rotationally track the target bone in mch.master
            self.make_constraint(mch.master, 'DAMPED_TRACK', ctrl.target)
            
    ####################################################
    # ORG bone

    @stage.parent_bones
    def parent_org_chain(self):
        if self.params.create_master_rig:
            super().parent_org_chain()
            
    ####################################################
    # Deform bones

    @stage.generate_bones
    def make_deform_bone(self):
        org = self.bones.org
        deform = self.bones.deform
        
        if self.params.create_master_rig:
            deform.master = self.copy_bone(
                org, make_derived_name(org, 'def', '_master'), scale=3 / 2)

        if self.params.make_deform and self.params.connect_eyelids:
            deform.eye = self.copy_bone(org, make_derived_name(org, 'def'))
            if self.params.create_iris_rig:
                deform.iris = self.copy_bone(
                    org, make_derived_name(org, 'def', '_iris'), scale=1 / 2)
                put_bone(self.obj, deform.iris, self.get_bone(org).tail)
                
        if not self.params.connect_eyelids:
            if self.params.create_iris_rig:
                deform.iris = self.copy_bone(
                        org, make_derived_name(org, 'def', '_iris'), scale=1 / 2)
                put_bone(self.obj, deform.iris, self.get_bone(org).tail)
            # without eyelids this is its only purpose
            deform.eye = self.copy_bone(org, make_derived_name(org, 'def'))

    @stage.parent_bones
    def parent_deform_chain(self):
        deform = self.bones.deform
        if self.params.create_master_rig:
            self.set_bone_parent(deform.master, self.bones.org)

        if self.params.make_deform:
            self.set_bone_parent(deform.eye, self.bones.mch.master)
            if self.params.create_iris_rig:
                self.set_bone_parent(deform.iris, deform.eye)

        elif not self.params.connect_eyelids and self.params.create_iris_rig:
            self.set_bone_parent(deform.iris, deform.eye)
            
    @stage.configure_bones
    def configure_control(self):
        bone = self.get_bone(self.bones.ctrl.target)
        bone.lock_rotation = (True, True, False)
        bone.lock_rotation_w = False

    @stage.rig_bones
    def rig_deform_chain(self):
        if self.params.create_iris_rig:
            # Copy XZ local scale from the eye target control
            self.make_constraint(
                self.bones.deform.iris, 'COPY_SCALE', self.bones.ctrl.target,
                owner_space='LOCAL', target_space='LOCAL_OWNER_ORIENT', use_y=False,
            )
        elif not self.params.make_deform:
            self.make_constraint(
                self.bones.deform.eye, 'COPY_SCALE', self.bones.ctrl.target,
                owner_space='LOCAL', target_space='LOCAL_OWNER_ORIENT'
            )
            
        if not self.params.create_iris_rig and self.params.extra_transforms:
            self.make_constraint(
                self.bones.deform.eye, 'COPY_SCALE', self.bones.ctrl.target,
                owner_space='LOCAL', target_space='LOCAL_OWNER_ORIENT'
            )
            self.make_constraint(
                self.bones.deform.eye, 'COPY_ROTATION', self.bones.ctrl.target,
                owner_space='LOCAL', target_space='LOCAL_OWNER_ORIENT', use_z=False, use_x=False
            )

    
    # -------------------------------------------------------------------------
    # PARAMETERS
    # -------------------------------------------------------------------------

    @classmethod
    def add_parameters(cls, params):
        """ Add the parameters of this rig type to the
                RigifyParameters PropertyGroup
        """
        params.eye_group = bpy.props.IntProperty(
            name="Eye Group",
            default=0,
            description="Eyes with same eye group get an own controller."
        )
        
        params.create_iris_rig = bpy.props.BoolProperty(
            name="Create Iris Rig",
            default=True,
            description="Create bones for iris control"
        )

        params.create_master_rig = bpy.props.BoolProperty(
            name="Create Master Rig",
            default=True,
            description="Create a master bone that moves the whole eye"
        )
        params.connect_eyelids = bpy.props.BoolProperty(
            name="Connect Face Eyelids",
            default=True,
            description="When set, rigs eyelids to follow the looking direction. Eye must be part of Rigify face."
        )
        params.master_offset = bpy.props.FloatProperty(
            name="Master Offset",
            default=0,
            description="Position of the master bone relative to the eye bone, if not using 'Connect Face Eyelids'."
        )
        params.extra_transforms = bpy.props.BoolProperty(
            name="Transfer Control Rot+Scale",
            default=False,
            description="Make scale and z rotation of the control bone available on the eye deform bone via constraints."
        )

        super().add_parameters(params)

    @classmethod
    def parameters_ui(cls, layout, params):
        col = layout.column()
        
        col.prop(params, "eye_group")

        col.prop(params, "create_master_rig", text="Create Master")
        if params.create_master_rig and not params.connect_eyelids:
            col.prop(params, "master_offset", text="Master Position")
            
        col.prop(params, "create_iris_rig", text="Create Iris")
        if not params.create_iris_rig:
            col.prop(params, "extra_transforms", text="Extra Transforms")
        col.prop(params, "connect_eyelids", text="Use Eyelids")
        
        if params.connect_eyelids:
            col.prop(params, "make_deform", text="Eyeball And Iris Deforms")
            col.prop(params, "eyelid_detach_option")

            col.prop(params, "eyelid_follow_split")

            row = col.row(align=True)
            row.prop(params, "eyelid_follow_default",
                    index=0, text="Follow X", slider=True)
            row.prop(params, "eyelid_follow_default",
                    index=1, text="Follow Z", slider=True)


class MultipleEyeClusterControl(EyeClusterControl):
    def find_cluster_rigs(self):
        """Finds and registers all eyes that belong to this group."""
        owner = self.owner
        owner.cluster_control = self
        self.rig_list = [owner]
        my_group = owner.params.eye_group  # current eye group

        parent_rig = owner.rigify_parent
        if parent_rig:
            for rig in parent_rig.rigify_children:
                # test group ID also
                if isinstance(rig, Rig) and rig != owner and rig.params.eye_group == my_group:
                    rig.cluster_control = self
                    self.rig_list.append(rig)

        self.rig_count = len(self.rig_list)
        
    def generate_widgets(self):
        # force remove old controller shape and prepare the generator
        widget_name = WGT_PREFIX + self.owner.generator.obj.name + '_' + self.master_bone
        for obj in list(self.owner.generator.widget_collection.objects):
            if obj.name == widget_name:
                if self.master_bone in self.owner.generator.old_widget_table:
                    del self.owner.generator.old_widget_table[self.master_bone]
                
                bpy.data.objects.remove(obj)
                break
        
        super().generate_widgets()
    

def create_sample(obj):
    bones = skin_eye_sample(obj)
    
    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['eye.L']]
    pbone.rigify_type = 'face.configurable_eye'
    bpy.ops.object.mode_set(mode='EDIT')
    
    return bones
