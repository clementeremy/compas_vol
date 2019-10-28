# from direct.showbase.ShowBase import ShowBase
from panda3d.core import *
from direct.gui.OnscreenText import OnscreenText

from direct.filter.FilterManager import FilterManager
from direct.filter.CommonFilters import CommonFilters

import numpy as np
# import compas_vol.raymarching.remapping_functions

from direct.filter.CommonFilters import CommonFilters

from direct.gui.DirectGui import DirectSlider
from direct.gui.DirectGui import *

from direct.task import Task

import compas_vol.raymarching.shaders.shader_path as shader_path
import compas_vol.raymarching.translator as translator

text_color_alpha = 0.5

class RayMarchingFactory:
    """
    Has all the necessary functionality that concerns the implementation of raymarching using GLSL shaders.

    Parameters
    ----------
    main_path  : the absolute path of the directory where the main.py is (i.e. the python file that runs the whole thing, can have any name) 
    renderer_  : instance of the class pandaRenderer.PandaRenderer that is used to render the scene
    translator_: instance of the class translator.Translator that has been initialized with the volumetric object that we want to display 

    """

    def __init__(self, main_path_ , renderer_, translator_, bounding_sphere = [0,0,0,20]):

        self.main_path = main_path_

        self.renderer = renderer_
        self.translator = translator_

        self.shader_quad = None
        self.ray_marching_quad = None

        self.bounding_sphere = bounding_sphere
        print ("self.bounding_sphere : ", self.bounding_sphere)

        ## GUI 
        self.display_target_object = [1]
        self.slicers = []
    
    ### ---------------------------------------------------------------- Ray marching shader
    def ray_marching_shader(self, default_fragment_shader = True, custom_fragment_shader = None): 
        """
        Creates a quad and applies to it a vertex shader which makes it stick to the viewport as if it was 2D.
        It also applies a fragment shader which has the implementation raymarching, and sends to the fragment shader all the necessary data.
        Finally it creates a tast to update the fragment shader data that needs to be updated in every frame.
        This is happening during the rendering of the scene and is overlayed on the existing pixels, as a result there is no depth culling.
        Works both on Windows and on Macbook.
        """

        #Create plane 2D on which to use the shader
        format = GeomVertexFormat.getV3() # vec3 vertex, vec4 color
        vdata = GeomVertexData('plane_2d', format, Geom.UHStatic)
        vdata.setNumRows(4)
        vertex_writer = GeomVertexWriter(vdata , 'vertex')

        #write vertices
        verts = [[-1,-1,0],[-1,1,0],[1,1,0],[1,-1,0]]
        for i,v in enumerate(verts): 
            vertex_writer.addData3f(v[0], v[1], v[2])
        

        #create primitives 
        geom = Geom(vdata)
        faces = [[0,1,2],[2,3,0]]
        for f in faces:
            triangle = GeomTriangles(Geom.UHStatic)
            triangle.addVertices(f[0],f[1],f[2])
            triangle.close_primitive()
            geom.addPrimitive(triangle)

        node = GeomNode("Plane_2D_node")
        node.addGeom(geom)
        self.shader_quad = NodePath(node)
        self.shader_quad.setTwoSided(True)
        self.renderer.render.attachNewNode(node)  

        ## this nodePath shouldn't affect the depth buffer
        self.shader_quad.setDepthWrite(False) 
        self.shader_quad.setDepthTest(False) 

        ### load ray marching shader
        if default_fragment_shader: 
            myShader = self.create_default_fragment_shader()
        else: 
            if custom_fragment_shader:
                myShader = Shader.load(Shader.SL_GLSL , shader_path.get_shader_path(self.main_path, "vshader_ray_marching.glsl"),\
                                                        shader_path.get_shader_path(self.main_path, custom_fragment_shader))    
            else: 
                print ("Attention! No shader provided for the post processing filter")
                return None

        ### apply shader 
        self.shader_quad.setShader(myShader)

        ### set shader inputs 
        self.shader_quad.setShader(myShader)
        self.shader_quad.setShaderInput("u_resolution" , self.renderer.getSize())
        self.shader_quad.setShaderInput("camera_POS", self.renderer.camera.getPos() - self.renderer.camera_start_position)
        self.shader_quad.setShaderInput("camera_START_POS", self.renderer.camera_start_position)
        self.shader_quad.setShaderInput("bounding_sphere" , self.bounding_sphere)
        
        self.shader_quad.setShaderInput("v_indices", self.translator.indices)
        self.shader_quad.setShaderInput("v_ids", self.translator.ids)
        self.shader_quad.setShaderInput("v_object_geometries_data", self.translator.object_geometries_data)  
        self.shader_quad.setShaderInput("v_data_count_per_object", self.translator.data_count_per_object)  

        self.shader_quad.setShaderInput("y_slice", -1000.) ## value far away from the model if slicer is not defined

        #activate alpha blending 
        self.shader_quad.setTransparency(TransparencyAttrib.MAlpha)

        #avoid culling of the object
        self.shader_quad.node().setBounds(OmniBoundingVolume())
        self.shader_quad.node().setFinal(True)
        self.renderer.taskMgr.add(self.task_update_ray_marching_shader, "task_update_ray_marching_shader")

##camera_START_POS
    def task_update_ray_marching_shader (self, task):

        
        self.shader_quad.set_shader_input("camera_POS", self.renderer.camera.getPos() + self.renderer.camera_start_position )
        self.shader_quad.set_shader_input("display_target_object", self.display_target_object[0]) 

        # if task.time % 5 == 0:
        #     print (self.display_target_object[0])
        return task.cont 

    def create_default_fragment_shader(self):
        parts = [] 
        #verterx shader
        with open( shader_path.get_shader_path( self.main_path, "vshader_ray_marching.glsl") , 'r') as shader:
            parts.append(shader.read())
        v_shader_full_code = "\n".join(parts)
        parts = []
        #fragments shaders
        with open(shader_path.get_shader_path( self.main_path, "fshader_1_translations.glsl"), "r") as shader:
            parts.append(shader.read())
        with open(shader_path.get_shader_path( self.main_path,"fshader_2_extras.glsl"), "r") as shader:
            parts.append(shader.read())  
        with open(shader_path.get_shader_path( self.main_path,"fshader_3_raymarching.glsl"), "r") as shader:
            parts.append(shader.read())  
        with open(shader_path.get_shader_path( self.main_path,"fshader_4_simple_shader_main.glsl"), "r") as shader:
            parts.append(shader.read())          
        f_shader_full_code = "\n".join(parts)
        myShader = Shader.make(Shader.SL_GLSL, v_shader_full_code, f_shader_full_code)

        return myShader


    ### ---------------------------------------------------------------- Ray marching in post-processing filter 
    """
    Creates a post processing filter of the scene, and applies to it a fragment shader with the implementation of raymarching.
    Sends all the necessary data to the fragment shader and creates a task to update in every frame the data that needs to be updated.
    The difference with the function 'ray_marching_shader' is that it alsso evaluates the depth buffer and performs depth culling. 
    (So far) works only on Windows. 
    """
    def post_processing_ray_marching_filter(self, default_fragment_shader = True, custom_fragment_shader = None):

        manager = FilterManager(self.renderer.win, self.renderer.cam)
        



        color_texture = Texture()
        depth_buffer = Texture()

        self.ray_marching_quad = manager.renderSceneInto(colortex = color_texture, depthtex = depth_buffer)

        ### load ray marching shader
        if default_fragment_shader: 
            myShader = self.create_default_post_processing_fragment_shader()
            # myShader = Shader.load(Shader.SL_GLSL , shader_path.get_shader_path(self.main_path, "vshader.glsl"),\
            #                                         shader_path.get_shader_path(self.main_path, "TEMPORARY_fshader_postprocessing.glsl"))               
        else: 
            if custom_fragment_shader:
                myShader = Shader.load(Shader.SL_GLSL , shader_path.get_shader_path(self.main_path, "vshader.glsl"),\
                                                        shader_path.get_shader_path(self.main_path, custom_fragment_shader))   
            else: 
                print ("Attention! No shader provided for the post processing filter")
                return None

        if myShader.getErrorFlag():
            print ("EROR") ## need to expand on this 

        ### apply shader 
        self.ray_marching_quad.setShader(myShader)    

        ### set shader inputs
        self.ray_marching_quad.setShaderInput("u_resolution" , self.renderer.getSize())
        self.ray_marching_quad.setShaderInput("color_texture", color_texture)
        self.ray_marching_quad.setShaderInput("depth_buffer", depth_buffer)
        self.ray_marching_quad.set_shader_input("camera_POS", self.renderer.camera.getPos())
        self.ray_marching_quad.setShaderInput("bounding_sphere" , self.bounding_sphere)
        self.ray_marching_quad.setShaderInput('myCamera', self.renderer.camera)

        proj_matrix_inv =  self.renderer.camLens.getProjectionMatInv()
        transform_coordinate_system =  LMatrix4.convertMat( self.renderer.camLens.getCoordinateSystem() , self.renderer.win.getGsg().getCoordinateSystem()  )
        view_matrix = self.renderer.camera.getTransform(self.renderer.render).getMat()
        transform_clip_plane_to_world = transform_coordinate_system * proj_matrix_inv * view_matrix  

        self.ray_marching_quad.setShaderInput("transform_clip_plane_to_world", transform_clip_plane_to_world)
        self.ray_marching_quad.setShaderInput("v_indices", self.translator.indices)
        self.ray_marching_quad.setShaderInput("v_ids", self.translator.ids)
        self.ray_marching_quad.setShaderInput("v_object_geometries_data", self.translator.object_geometries_data)  
        self.ray_marching_quad.setShaderInput("v_data_count_per_object", self.translator.data_count_per_object)  

        self.ray_marching_quad.setShaderInput("y_slice", -1000.) ## value far away from the model if slicer is not defined

        self.renderer.taskMgr.add(self.update_filter, "update_filter")

    def update_filter (self, task):       
        self.ray_marching_quad.set_shader_input("camera_POS", self.renderer.camera.getPos())
        proj_matrix_inv =  self.renderer.camLens.getProjectionMatInv()
        transform_coordinate_system = LMatrix4.convertMat( self.renderer.camLens.getCoordinateSystem() , self.renderer.win.getGsg().getCoordinateSystem())
        view_matrix = self.renderer.camera.getTransform(self.renderer.render).getMat()
        transform_clip_plane_to_perspective_camera = transform_coordinate_system * proj_matrix_inv * view_matrix 
        self.ray_marching_quad.setShaderInput("transform_clip_plane_to_perspective_camera", transform_clip_plane_to_perspective_camera)

        self.ray_marching_quad.set_shader_input("display_target_object", self.display_target_object[0]) ## ATTENTION< THIS SHOULD ONLY BE HAPPENING WHEN THE GUI BUTTONS ARE PRESSED!
        return task.cont   

    def create_default_post_processing_fragment_shader(self):
        ### Create shader glsl files. This is done in order to be able to split the big shader in separate glsl files for better organisation
        parts = [] 
        #verterx shader
        with open(shader_path.get_shader_path( self.main_path, "vshader.glsl") , 'r') as shader:
            parts.append(shader.read())
        v_shader_full_code = "\n".join(parts)
        parts = []
        #fragments shaders
        with open(shader_path.get_shader_path( self.main_path, "fshader_1_translations.glsl"), "r") as shader:
            parts.append(shader.read())
        with open(shader_path.get_shader_path( self.main_path,"fshader_2_extras.glsl"), "r") as shader:
            parts.append(shader.read())  
        with open(shader_path.get_shader_path( self.main_path,"fshader_3_raymarching.glsl"), "r") as shader:
            parts.append(shader.read())  
        with open(shader_path.get_shader_path( self.main_path,"fshader_4_post_processing_main.glsl"), "r") as shader:
            parts.append(shader.read())          
        f_shader_full_code = "\n".join(parts)
        myShader = Shader.make(Shader.SL_GLSL, v_shader_full_code, f_shader_full_code)

        return myShader


    ### ---------------------------------------------------------------- Slicing y plane
    def create_slicer(self, range_a = 0, range_b = 100, start_value = 0, axis = 'y', screen_position = -0.8):
        """
        Creates a slider that slices the model with a plane parallel to the y axis.
        (removed) It also creates a line to show the position of the slicing plane.
        Finally it sends data to the fragment shader every time the slider is modified.

        Parameters
        ----------
        range_a     : (float) Lower boundary of slider values.
        range_b     : (float) Upper boundary of slider values.
        start_value : (float) Start value of the slider.
        """
        generator_slice_plane = None
        # generator_slice_plane = self.create_slicer_dynamic_geom_generator()

        slicer_index = len(self.slicers)

        slicer = DirectSlider(range=(range_a,range_b), value=start_value, pageSize=3, command=self.event_update_slicer, extraArgs = [generator_slice_plane , axis, slicer_index])

        slicer.reparentTo(self.renderer.aspect2d)
        slicer.setPos(0,0, screen_position)
        slicer.setScale(0.25,0.25,0.25)

        self.slicers.append(slicer)

        title_of_slider = OnscreenText(text = "Slice model, axis : " + axis , pos = (-0.55, screen_position), scale = 0.045, fg = (0.,0.,0.,text_color_alpha)) ,
        min_of_slider = OnscreenText(text = str(range_a), pos = (-0.3, -0.8), scale = 0.035, fg = (0.,0.,0.,text_color_alpha))
        max_of_slider = OnscreenText(text = str(range_b), pos = (0.3, -0.8), scale = 0.035, fg = (0.,0.,0.,text_color_alpha))

        ## initialize slicer values on shader 
        if self.ray_marching_quad:
            self.ray_marching_quad.setShaderInput("y_slice", -19)
            self.ray_marching_quad.setShaderInput("z_slice", 19)
        if self.shader_quad: 
            self.ray_marching_quad.setShaderInput("y_slice", -19)
            self.ray_marching_quad.setShaderInput("z_slice", 19)

    def event_update_slicer(self, generator_slice_plane, axis, slicer_index):
        my_slice = self.slicers[slicer_index]['value']

        if axis == 'y':
            if self.ray_marching_quad:
                self.ray_marching_quad.setShaderInput("y_slice", my_slice)
            if self.shader_quad: 
                self.shader_quad.setShaderInput("y_slice", my_slice)
        else: # axis = 'z':
            if self.ray_marching_quad:
                self.ray_marching_quad.setShaderInput("z_slice", my_slice)
            if self.shader_quad: 
                self.shader_quad.setShaderInput("z_slice", my_slice)                   

        # self.update_slicer_dynamic_geom(generator_slice_plane, my_slice)


    # def create_slicer_dynamic_geom_generator(self):
    #     ## display outline of slicing plane as dynamic geometry 
    #     generator_slice_plane = MeshDrawer()
    #     generator_slice_plane.setBudget(100)

    #     nodePath_slice_plane = generator_slice_plane.getRoot()
    #     nodePath_slice_plane.reparentTo(self.renderer.render)
    #     nodePath_slice_plane.setDepthWrite(False)
    #     # nodePath_slice_plane.setTransparency(True)
    #     nodePath_slice_plane.setTwoSided(True)
    #     nodePath_slice_plane.setBin("fixed",0)
    #     nodePath_slice_plane.setLightOff(True)
    #     return generator_slice_plane

    # def update_slicer_dynamic_geom(self,generator_slice_plane, y_slice):
    #     ## update dynamic geometry 
    #     generator_slice_plane.begin(self.renderer.cam, self.renderer.render)
    #     z1 = -10
    #     z2 = 10
    #     x1 = -10
    #     x2 = 10

    #     # vertices = [[x1, y_slice, z1] , [x2, y_slice, z1] , [x2, y_slice, z2] , [x1, y_slice, z2]]
    #     vertices = [[x1, y_slice, z1], [x2, y_slice, z1]]
    #     for i, v in enumerate(vertices):
    #         v_next = vertices[(i+1)% len(vertices)]
    #         generator_slice_plane.crossSegment(LVector3(v[0], v[1], v[2]), \
    #                                            LVector3(v_next[0], v_next[1], v_next[2]), \
    #                                            LVector4(1,1,1,1), 0.04, \
    #                                            LVector4(0.6,0.6,0.6,1.)) #start, stop, frame, thickness, color)

    #     generator_slice_plane.end()


### ---------------------------------------------------------------- GUI
    def show_csg_tree_GUI(self):        
        """
        Creates and displays the CSG tree on the screen. 
        This tree is interactive, i.e. you can click on an object to display it and all its children.
        Also it creates a task to send the tree-selection data to the fragment shader every frame (SHOULD INSTEAD BE AN EVENT) 

        """
        ## show lines of GUI
        format = GeomVertexFormat.getV3c4() # vec3 vertex, vec4 color
        vdata = GeomVertexData('GUI_lines', format, Geom.UHStatic)
        vdata.setNumRows(20) # 20 vertices in total
        vertex_writer = GeomVertexWriter(vdata , 'vertex')
        color_writer  = GeomVertexWriter(vdata , 'color')

        disp_parent = LVector3f (-0.06 ,0, -0.02)
        disp_self2 = LVector3f (-0.15,0, 0)
        disp_self = LVector3f (-0.1,0, 0)

        ## create buttons
        buttons  = []
        vertices = []
        for obj in self.translator.objects_unwrapped_list:
            i         = obj.index
            order     = obj.order
            id        = obj.id
            position = LVector3f(0.8 + order * 0.09, 0 ,0.95 - i * 0.06)

            buttons.append( DirectRadioButton(text = " " + str(i)  + " " + translator.get_obj_name(id) + " " ,\
                                              variable = self.display_target_object, value= [i], scale=0.03,\
                                              pos= position ) ) #, command = set_input_of_shader(i)
            
            if i>1 : #then connect object with parent 
                vertices.append( LVector3f(0.8 + (order-1) * 0.09, 0 ,0.95 - obj.parent_index * 0.06) + disp_parent ) 
                vertices.append(position + disp_self2 )
                vertices.append(position + disp_self )

        for button in buttons:
            button.setOthers(buttons)

        for i,v in enumerate(vertices): 
            vertex_writer.addData3f(v[0] , v[1] , v[2])     ###fg = (0.,0.,0.,text_color_alpha)
            color_writer.addData4f(0. , 0. , 0., text_color_alpha) 

        ## Create lines connecting buttons 
        #create primitives 
        geom = Geom(vdata)

        for i,v in enumerate(vertices):
            if i< len(vertices)-1 and (i+1) % 3 != 0 :
                line = GeomLines(Geom.UHStatic)
                line.addVertices(i,i+1)
                line.close_primitive()
                geom.addPrimitive(line)

        ## Node in graph 
        node = GeomNode('GUI_lines')
        node.addGeom(geom)

        #Nodepath
        nodePath = NodePath(node)
        nodePath.setRenderModeThickness(1.3)
        nodePath.setTwoSided(True)
        nodePath.setScale(1,1,1)
        nodePath = self.renderer.aspect2d.attachNewNode(node)  
        # nodePath.reparentTo(self.nodePath_points_lines_group) 