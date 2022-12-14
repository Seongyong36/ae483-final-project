#include "controller_ae483.h"
#include "stabilizer_types.h"
#include "power_distribution.h"
#include "log.h"
#include "param.h"
#include "num.h"
#include "math3d.h"


// Sensor measurements
// - tof (from the z ranger on the flow deck)
static uint16_t tof_count = 0;
static float tof_distance = 0.0f;
// - flow (from the optical flow sensor on the flow deck)
static uint16_t flow_count = 0;
static float flow_dpixelx = 0.0f;
static float flow_dpixely = 0.0f;

// Lab 9 addition
static bool use_observer = false;
static bool reset_observer = false;

// State
static float o_x = 0.0f;
static float o_y = 0.0f;
static float o_z = 0.0f;
static float psi = 0.0f;
static float theta = 0.0f;
static float phi = 0.0f;
static float v_x = 0.0f;
static float v_y = 0.0f;
static float v_z = 0.0f;
static float w_x = 0.0f;
static float w_y = 0.0f;
static float w_z = 0.0f;

// Setpoint
static float o_x_des = 0.0f;
static float o_y_des = 0.0f;
static float o_z_des = 0.0f;

// Input
static float tau_x = 0.0f;
static float tau_y = 0.0f;
static float tau_z = 0.0f;
static float f_z = 0.0f;

// Motor power command
static uint16_t m_1 = 0;
static uint16_t m_2 = 0;
static uint16_t m_3 = 0;
static uint16_t m_4 = 0;
// Measurements
static float n_x = 0.0f;
static float n_y = 0.0f;
static float r = 0.0f;
static float a_z = 0.0f;

// FINAL PROJECT ADDITION
static float lh_x = 0.0f;
static float lh_y = 0.0f;
static float lh_z = 0.0f;

// Constants
// static float k_flow = 4.09255568f;
static float g = 9.81f;
static float dt = 0.002f;
// static float o_z_eq = 0.5f; // FIXED: replaced with your choice of equilibrium height

// Measurement errors
// static float n_x_err = 0.0f;
// static float n_y_err = 0.0f;
// static float r_err = 0.0f;
static float lh_x_err;
static float lh_y_err;
static float lh_z_err;

void ae483UpdateWithTOF(tofMeasurement_t *tof)
{
  tof_distance = tof->distance;
  tof_count++;
}

void ae483UpdateWithFlow(flowMeasurement_t *flow)
{
  flow_dpixelx = flow->dpixelx;
  flow_dpixely = flow->dpixely;
  flow_count++;
}

void ae483UpdateWithLH(float x, float y, float z) 
{
    lh_x = x;
    lh_y = y;
    lh_z = z; //lh-> ae483_lh_z;
}
void ae483UpdateWithDistance(distanceMeasurement_t *meas)
{
  // If you have a loco positioning deck, this function will be called
  // each time a distance measurement is available. You will have to write
  // code to handle these measurements. These data are available:
  //
  //  meas->anchorId  uint8_t   id of anchor with respect to which distance was measured
  //  meas->x         float     x position of this anchor
  //  meas->y         float     y position of this anchor
  //  meas->z         float     z position of this anchor
  //  meas->distance  float     the measured distance
}

void ae483UpdateWithPosition(positionMeasurement_t *meas)
{
  // This function will be called each time you send an external position
  // measurement (x, y, z) from the client, e.g., from a motion capture system.
  // You will have to write code to handle these measurements. These data are
  // available:
  //
  //  meas->x         float     x component of external position measurement
  //  meas->y         float     y component of external position measurement
  //  meas->z         float     z component of external position measurement
}

void ae483UpdateWithPose(poseMeasurement_t *meas)
{
  // This function will be called each time you send an external "pose" measurement
  // (position as x, y, z and orientation as quaternion) from the client, e.g., from
  // a motion capture system. You will have to write code to handle these measurements.
  // These data are available:
  //
  //  meas->x         float     x component of external position measurement
  //  meas->y         float     y component of external position measurement
  //  meas->z         float     z component of external position measurement
  //  meas->quat.x    float     x component of quaternion from external orientation measurement
  //  meas->quat.y    float     y component of quaternion from external orientation measurement
  //  meas->quat.z    float     z component of quaternion from external orientation measurement
  //  meas->quat.w    float     w component of quaternion from external orientation measurement
}

void ae483UpdateWithData(const struct AE483Data* data)
{
  // This function will be called each time AE483-specific data are sent
  // from the client to the drone. You will have to write code to handle
  // these data. For the example AE483Data struct, these data are:
  //
  //  data->x         float
  //  data->y         float
  //  data->z         float
  //
  // Exactly what "x", "y", and "z" mean in this context is up to you.
}


void controllerAE483Init(void)
{
  // Do nothing
}

bool controllerAE483Test(void)
{
  // Do nothing (test is always passed)
  return true;
}

void controllerAE483(control_t *control,
                     setpoint_t *setpoint,
                     const sensorData_t *sensors,
                     const state_t *state,
                     const uint32_t tick)
{
    if (RATE_DO_EXECUTE(ATTITUDE_RATE, tick)) {
    // Everything in here runs at 500 Hz

    // Desired position
    o_x_des = setpoint->position.x;
    o_y_des = setpoint->position.y;
    o_z_des = setpoint->position.z;

    // Measurements
    w_x = radians(sensors->gyro.x);
    w_y = radians(sensors->gyro.y);
    w_z = radians(sensors->gyro.z);
    a_z = g * sensors->acc.z;
    n_x = flow_dpixelx;
    n_y = flow_dpixely;
    r = tof_distance;

    if (reset_observer) {
      o_x = 0.0f;
      o_y = 0.0f;
      o_z = 0.0f;
      psi = 0.0f;
      theta = 0.0f;
      phi = 0.0f;
      v_x = 0.0f;
      v_y = 0.0f;
      v_z = 0.0f;
      reset_observer = false;
    }

    // State estimates
    if (use_observer) {
    
      // Compute each element of:
      // 
      //   C x + D u - y
      
      // // FIXED
      // n_x_err = k_flow / o_z_eq * v_x - k_flow * w_y - n_x ;
      // n_y_err = k_flow / o_z_eq * v_y + k_flow * w_x - n_y; 
      // r_err = o_z - r;
      // // Update estimates
      // o_x += dt * v_x;
      // o_y += dt * v_y;
      // psi += dt * w_z;

      // o_z += dt * (- 15.0519932234904f*o_z + 15.0519932234904f*r + 1.0f*v_z);
      // theta += dt * (0.00143420551807967f*n_x - 0.0117391318771912f*v_x + 1.0058695659386f*w_y);
      // phi += dt * (- 0.00113190351037395f*n_y + 0.00926475628006708f*v_y + 1.00463237814003f*w_x);
      // v_x += dt * (0.059508540238655f*n_x + 9.81f*theta - 0.487084028665624f*v_x + 0.243542014332812f*w_y);
      // v_y += dt * (0.0526580116544559f*n_y - 9.81f*phi - 0.43101168933586f*v_y - 0.21550584466793f*w_x);
      // v_z += dt * (1.0f*a_z - 1.0f*g - 60.7500000000004f*o_z + 60.7500000000004f*r);
      // FIXED

      // FINAL PROJECT OBSERVER 
      lh_x_err = o_x - lh_x;
      lh_y_err = o_y - lh_y;
      lh_z_err = o_z - lh_z;
      o_x += dt * (-17.758181912487f *lh_x_err + 1.0f*v_x );
      o_y += dt * (-17.722312157029f *lh_y_err + 1.0f*v_y );
      o_z += dt * (-21.430118991736f *lh_z_err + 1.0f*v_z );
      psi += dt * (w_z);
      theta += dt * (-34.333333333333f *lh_x_err + w_y );
      phi += dt * (-50.75f *-lh_y_err + w_x );
      v_x += dt * (-120.12095686293f *lh_x_err + 9.81f*theta );
      v_y += dt * (-135.91517409559f *lh_y_err - 9.81f*phi );
      v_z += dt * (a_z - g - 93.5f*lh_z_err );
      
    } else {
      o_x = state->position.x;
      o_y = state->position.y;
      o_z = state->position.z;
      psi = radians(state->attitude.yaw);
      theta = - radians(state->attitude.pitch);
      phi = radians(state->attitude.roll);
      v_x = state->velocity.x*cosf(psi)*cosf(theta) + state->velocity.y*sinf(psi)*cosf(theta) - state->velocity.z*sinf(theta);
      v_y = state->velocity.x*(sinf(phi)*sinf(theta)*cosf(psi) - sinf(psi)*cosf(phi)) + state->velocity.y*(sinf(phi)*sinf(psi)*sinf(theta) + cosf(phi)*cosf(psi)) + state->velocity.z*sinf(phi)*cosf(theta);
      v_z = state->velocity.x*(sinf(phi)*sinf(psi) + sinf(theta)*cosf(phi)*cosf(psi)) + state->velocity.y*(-sinf(phi)*cosf(psi) + sinf(psi)*sinf(theta)*cosf(phi)) + state->velocity.z*cosf(phi)*cosf(theta);
    }


    if (setpoint->mode.z == modeDisable) {
      // If there is no desired position, then all
      // motor power commands should be zero

      powerSet(0, 0, 0, 0);
    } else {
      // Otherwise, motor power commands should be
      // chosen by the controller

      // // For Lab
      // tau_x = 0.00206453f * (o_y - o_y_des) -0.00356916f * phi + 0.00129335f * v_y -0.00052481f * w_x;
      // tau_y = -0.00319835f * (o_x - o_x_des) -0.00417561f * theta -0.00170095f * v_x -0.00055222f * w_y;
      // tau_z = -0.00098990f * psi -0.00101293f * w_z;
      // f_z = -0.47034538f * (o_z - o_z_des) -0.17971982f * v_z + 0.30607200f;

      // m_1 = limitUint16( -3622138.5f * tau_x -3622138.5f * tau_y -6756756.8f * tau_z + 123152.7f * f_z );
      // m_2 = limitUint16( -3622138.5f * tau_x + 3622138.5f * tau_y + 6756756.8f * tau_z + 123152.7f * f_z );
      // m_3 = limitUint16( 3622138.5f * tau_x + 3622138.5f * tau_y -6756756.8f * tau_z + 123152.7f * f_z );
      // m_4 = limitUint16( 3622138.5f * tau_x -3622138.5f * tau_y + 6756756.8f * tau_z + 123152.7f * f_z );

      // For Final Project 
      
      tau_x = 0.00398188f * (o_y - o_y_des) -0.00453614f * phi + 0.00196993f * v_y -0.00055739f * w_x;
      tau_y = -0.00487679f * (o_x - o_x_des) -0.00487960f * theta -0.00224716f * v_x -0.00056757f * w_y;
      tau_z = -0.00101816f * psi -0.00030581f * w_z;
      f_z = -0.36393952f * (o_z - o_z_des) -0.16505088f * v_z + 0.34335000f;

      m_1 = limitUint16( -3827018.8f * tau_x -3827018.8f * tau_y -33467202.1f * tau_z + 128205.1f * f_z );
      m_2 = limitUint16( -3827018.8f * tau_x + 3827018.8f * tau_y + 33467202.1f * tau_z + 128205.1f * f_z );
      m_3 = limitUint16( 3827018.8f * tau_x + 3827018.8f * tau_y -33467202.1f * tau_z + 128205.1f * f_z );
      m_4 = limitUint16( 3827018.8f * tau_x -3827018.8f * tau_y + 33467202.1f * tau_z + 128205.1f * f_z );

      // Apply motor power commands
      powerSet(m_1, m_2, m_3, m_4);
    }
  }
}

//              1234567890123456789012345678 <-- max total length
//              group   .name
LOG_GROUP_START(ae483log)
LOG_ADD(LOG_UINT16,         num_tof,                &tof_count)
LOG_ADD(LOG_UINT16,         num_flow,               &flow_count)
LOG_ADD(LOG_FLOAT,          o_x,                    &o_x)
LOG_ADD(LOG_FLOAT,          o_y,                    &o_y)
LOG_ADD(LOG_FLOAT,          o_z,                    &o_z)
LOG_ADD(LOG_FLOAT,          psi,                    &psi)
LOG_ADD(LOG_FLOAT,          theta,                  &theta)
LOG_ADD(LOG_FLOAT,          phi,                    &phi)
LOG_ADD(LOG_FLOAT,          v_x,                    &v_x)
LOG_ADD(LOG_FLOAT,          v_y,                    &v_y)
LOG_ADD(LOG_FLOAT,          v_z,                    &v_z)
LOG_ADD(LOG_FLOAT,          w_x,                    &w_x)
LOG_ADD(LOG_FLOAT,          w_y,                    &w_y)
LOG_ADD(LOG_FLOAT,          w_z,                    &w_z)
LOG_ADD(LOG_FLOAT,          o_x_des,                &o_x_des)
LOG_ADD(LOG_FLOAT,          o_y_des,                &o_y_des)
LOG_ADD(LOG_FLOAT,          o_z_des,                &o_z_des)
LOG_ADD(LOG_FLOAT,          tau_x,                  &tau_x)
LOG_ADD(LOG_FLOAT,          tau_y,                  &tau_y)
LOG_ADD(LOG_FLOAT,          tau_z,                  &tau_z)
LOG_ADD(LOG_FLOAT,          f_z,                    &f_z)
LOG_ADD(LOG_UINT16,         m_1,                    &m_1)
LOG_ADD(LOG_UINT16,         m_2,                    &m_2)
LOG_ADD(LOG_UINT16,         m_3,                    &m_3)
LOG_ADD(LOG_UINT16,         m_4,                    &m_4)
LOG_ADD(LOG_FLOAT,          n_x,                    &n_x)
LOG_ADD(LOG_FLOAT,          n_y,                    &n_y)
LOG_ADD(LOG_FLOAT,          r,                      &r)
LOG_ADD(LOG_FLOAT,          a_z,                    &a_z)
LOG_ADD(LOG_FLOAT,          lh_x,                    &lh_x)
LOG_ADD(LOG_FLOAT,          lh_y,                    &lh_y)
LOG_ADD(LOG_FLOAT,          lh_z,                    &lh_z)
LOG_GROUP_STOP(ae483log)

//                1234567890123456789012345678 <-- max total length
//                group   .name
PARAM_GROUP_START(ae483par)
PARAM_ADD(PARAM_UINT8,     reset_observer,            &use_observer)
PARAM_ADD(PARAM_UINT8,     use_observer,            &use_observer)
PARAM_GROUP_STOP(ae483par)
