#version 120

#ifdef GL_ES
precision mediump float;
#endif

#define resolution_of_texture 1024.
#define max_num 150 // CAREFUL! MEMORY

///---------------------------------------------------------------- INPUTS
uniform vec2 u_resolution;
uniform vec3 camera_POS;
uniform float osg_FrameTime;

//v_data
uniform vec4[max_num] v_data;
uniform int v_data_length;
uniform float[max_num] start_values;

uniform float y_slice;
uniform int vv;
uniform float slider_value;

//buffers
uniform sampler2D color_texture;
uniform sampler2D depth_buffer;

uniform mat4 transform_clip_plane_to_perspective_camera;


///---------------------------------------------------------------- SDF FUNCTIONS (from compas-vol)
///// PRIMITIVES 
#define VolSphere_id 100
#define VolBox_id 101
#define VolTorus_id 102
#define VolCylinder_id 103

float random (vec2 st) {
    return fract(sin(dot(st.xy, vec2(12.9898,78.233)))* 43758.5453123);
}

vec3 animate_point(in int current_index){
    float magnitude = random (vec2(current_index))  * 7.+ 1.;
    float frequency1 = random (vec2(current_index/3.56))  * 0.45  + 0.1;
    float offset  = random (vec2(current_index/3.56))  * 6.;
    float frequency = frequency1 * slider_value;
    // frequency *=  slider_value;
    return vec3(sin(osg_FrameTime * frequency) * magnitude, cos(offset +osg_FrameTime * frequency) * magnitude, sin(offset + osg_FrameTime * frequency) * magnitude);
}


float VolPrimitive(in vec3 p, in int id, in int current_index, in mat4 matrix, in vec4 size_xyzw){ //current_index only needed for 
    //VolSphere
    if (id == VolSphere_id){
        vec3 center = size_xyzw.xyz;
        // center = center + animate_point(current_index) ;
        float radius = size_xyzw.w;
        return length(p - center) - radius;
    //VolBox
    }else if (id == VolBox_id){
        float radius= size_xyzw.w;
        vec4 pos_transformed =  transpose(matrix) * vec4(p , 1.);
        vec3 d = abs(pos_transformed.xyz) - (size_xyzw.xyz * 0.5 - radius);
        return length(max(d, 0.0)) - radius + min(max(d.x,max(d.y,d.z)), 0.0);
    //VolTorus
    }else if (id == VolTorus_id){
        float center_radius = size_xyzw.x;
        float section_radius = size_xyzw.y;
        vec4 pos_transformed = transpose(matrix)  * vec4(p , 1.);
        float dxy = length(pos_transformed.xy);
        float d2 = sqrt((dxy - center_radius)*(dxy - center_radius) + pos_transformed.z*pos_transformed.z );
        return d2 - section_radius;
    //VolCylinder
    }else if (id == VolCylinder_id){
        float h = size_xyzw.x;
        float r = size_xyzw.y;
        vec4 pos_transformed = transpose(matrix) * vec4(p , 1.);
        float d = length(pos_transformed.xy) - r;
        return max(d, abs(pos_transformed.z) - h/2.);
    } else {
        return 0.;
    }
}


float yPlane(vec3 p, float y_of_plane){
    return -(p.y - y_of_plane);
}

///// COMBINATIONS
#define Union_id 200
#define Intersection_id 201
#define Smooth_Union_id 202

float VolCombination(in float a, in float b, in float id, in float r){
    //Union
    if (id == Union_id){
        return min(a , b);
    //Intersection
    } else if (id == Intersection_id){
        return max(a , b);
    //Smooth Union
    } else if (id == Smooth_Union_id){
        float h = min(max(0.5 + 0.5 * (b - a) / r, 0), 1);
        return (b * (1 - h) + h * a) - r * h * (1 - h);
    } else {
        return 0. ;
    }
}

///// MODIFICATIONS
#define Shell_id 300

//// ---- Shell
float Shell_get_distance( in float current_dist,  in float d,in float s){ // torus centered in origin. t: vec2(rad of center of torus, rad of section of torus)
    return abs(current_dist + (s - 0.5) * d) - d/2.0;
}


/////////////////////////////////////////////////////////////
float[max_num] values; 
float dist_final;
float dist;
int current_index;
int current_id;
int parent_index; 
int parent_id;
mat4 matrix;
vec4 size_xyzw;
vec4 parent_details_xyzw = vec4(0.); // only needed for a few combinations

float GetDistance(vec3 p){ //union of shapes  
    values = start_values;

    for (int i = 0; i < v_data_length-1; i+= 6){ 
        //---- get data
        current_index = int( v_data[i][0]);
        current_id = int( v_data[i][1]);
        parent_index = int( v_data[i][2] );
        parent_id = int( v_data[i][3]);
        matrix = mat4(v_data[i+1], v_data[i+2], v_data[i+3], v_data[i+4]);
        size_xyzw = vec4(v_data[i+5]);

        //---- update parent_details_xyzw only when needed 
        if (parent_id == Smooth_Union_id){ // or other combination types that need it 
            int pos = int(v_data[0][0]) - parent_index;
            parent_details_xyzw = v_data[pos*6 +5];
        }

        /////------------------- Get dist of CURRENT obj
        //primitive
        if (current_id == VolSphere_id || current_id == VolBox_id || current_id == VolTorus_id || current_id == VolCylinder_id){
            dist = VolPrimitive(p, current_id, current_index, matrix, size_xyzw);
            values[current_index] = dist;
        //combination
        } else if (current_id == Union_id || current_id ==  Intersection_id ||current_id ==  Smooth_Union_id ){
            dist = values[current_index];
        //modification
        } else if(current_id == Shell_id){ // Shell
            dist = Shell_get_distance(values[current_index] , size_xyzw.x, size_xyzw.y);
            values[current_index] = dist;  
        }

        /////------------------- send information to PARENT
        // combination
        if (parent_id == Union_id || parent_id ==  Intersection_id ||parent_id ==  Smooth_Union_id ){
            values[parent_index] = VolCombination(values[parent_index], dist, parent_id, parent_details_xyzw.x);  
        // modification
        } else if (parent_id == Shell_id){
            values[parent_index] = values[current_index]; 
        }

        /////------------------- break loop once the necessary values have been calculated
        if (current_index == vv || current_index == 0 ){
            dist_final = values[vv];

            // intersect wih slicing plane !!!!!!!!!!!!!!!HERE THIS SHOULD HAPPEN ONLY IF SLICING PLANE EXISTS
            float y_slice_plane_dist = yPlane(p, y_slice);
            return max(dist_final, y_slice_plane_dist);

            return dist_final;
        }
    }  
}


int total_steps = 0;

#define MAX_STEPS 200
#define MAX_DIST 200.
#define SURF_DIST 0.02
float RayMarch(vec3 ro, vec3 rd){ // ray origin, ray direction
    float dO = 0.; // distance from origin

    for (int i = 0;  i< MAX_STEPS; i++){
        vec3 p = ro + rd * dO;
        float dS = GetDistance(p); // Get distance scene
        dO += dS;
        total_steps += 1;
        if (dO> MAX_DIST || dS < SURF_DIST) break;
    }
    return dO;
}

vec3 GetNormal(vec3 p){
    float d = GetDistance(p);
    //evaluate distance of points around p
    vec2 e = vec2(.01 , 0); // very small vector
    vec3 n = d - vec3(GetDistance(p-e.xyy), // e.xyy = vec3(.01,0,0)
                      GetDistance(p-e.yxy),
                      GetDistance(p-e.yyx));
    return normalize(n);
}

float GetLight (vec3 p){ //gets the position of intersection of ray with shape
    vec3 LightPos = vec3(0 , 5, 6);
    // LightPos.xz += vec2( sin(u_time) , cos(u_time));

    vec3 l = normalize(LightPos - p); // vector from light source to position
    vec3 n = GetNormal(p);
    float dif = clamp(dot(n, l)  , 0., 1.);

    //compute shadows
    float d = RayMarch(p+n * SURF_DIST,l);
    if(d<length(LightPos -p)){
        dif *= .3;
    }
    return dif;
}



vec3 findRayDirection(in vec2 uv){
    vec4 pixel_world_coords =  transform_clip_plane_to_perspective_camera * vec4(uv.x, uv.y, 1., 1.);
    vec3 rd = pixel_world_coords.xyz;
    return normalize(rd);
}


///---------------------------------------------------------------- DEPTH  
vec3 World_position_from_depth(in float depth, in vec2 uv){
    vec2 st_ = uv * 2.0 - 1.0;          //translate 0s at the center of the image, range [-1,1]
    depth =  depth * 2.0 - 1.0;   //do the same for depth values 
    vec4 clipSpacePosition =  vec4(st_.x, st_.y, depth, 1.);
    vec4 viewSpacePosition = transform_clip_plane_to_perspective_camera * clipSpacePosition;
    viewSpacePosition /= viewSpacePosition.w; // Perspective division
    return viewSpacePosition.xyz;
    }



void main()
{
    vec2 st = gl_FragCoord.xy / u_resolution.xy;
    vec2 texture_uv = gl_FragCoord.xy / vec2(resolution_of_texture);

    // ------------- get information from buffers
    vec4 color_pixel = texture2D(color_texture, texture_uv.xy);  
    vec4 depth_pixel = texture2D(depth_buffer, texture_uv.xy); 

    // ------------- calculate distance of objects
    vec3 world_pos_object = World_position_from_depth(depth_pixel.x, st.xy);
    float dist_object = length(world_pos_object - camera_POS); //distance of rendered objects from camera 

    // ------------- ray marching 
    vec2 uv = 2*(st - vec2(0.5, 0.5)); //put 0 in the center of the window, range of values: [-1,1]
    vec3 ro = camera_POS.xyz; // ray origin : camera position (world coordinates)
    vec3 rd = findRayDirection(uv);
    float d = RayMarch(ro, rd);
    vec3 world_pos_SDF = ro + rd * d; // position of intersection of ray with solid

    float dist_SDF = length(world_pos_SDF - camera_POS); //distance of SDF in current position from camera 
    vec3 color_of_SDF = vec3(GetNormal(world_pos_SDF));

    // check depth and color accordingly
    vec3 color = vec3(0.);
    if (dist_object > dist_SDF && dist_SDF < 200){
       
        if (abs(world_pos_SDF.y - y_slice) < 0.1) {
            color = vec3(1.);  // color white section
        } else {
            color = color_of_SDF ; }
    } else {
        color = color_pixel.xyz;
    }

    // color = vec3( total_steps / 70. ); // display number of steps 
    gl_FragColor = vec4(color, 1.);
}