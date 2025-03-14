''' 
Simulation works 
Gradients do not work because intermediate results of global fields are not saved for the backward pass.
'''


import taichi as ti
import numpy as np
import time
import matplotlib.pyplot as plt

import os
this_dir = os.path.dirname(os.path.abspath(__file__))

# Initialize Taichi with Metal backend
ti.init(arch=ti.gpu)
# ti.init(arch=ti.cpu, cpu_max_num_threads=1)


# Parameters
n_systems = 1000
n_dof = 4
dt = 0.01
steps = 1000

# Taichi fields
q = ti.Vector.field(n_dof, dtype=ti.f32, shape=n_systems, needs_grad=True)  # Add needs_grad for debugging
q_dot = ti.Vector.field(n_dof, dtype=ti.f32, shape=n_systems, needs_grad=True)
q_ddot = ti.Vector.field(n_dof, dtype=ti.f32, shape=n_systems, needs_grad=True)
m = ti.field(dtype=ti.f32, shape=n_systems, needs_grad=True)
M = ti.Matrix.field(n_dof, n_dof, dtype=ti.f32, shape=n_systems, needs_grad=True)
C = ti.Matrix.field(n_dof, n_dof, dtype=ti.f32, shape=n_systems)
G = ti.Vector.field(n_dof, dtype=ti.f32, shape=n_systems, needs_grad=True)
tau = ti.Vector.field(n_dof, dtype=ti.f32, shape=n_systems)
loss = ti.field(dtype=ti.f32, shape=(), needs_grad=True)

# Add after other field definitions
# Store trajectory for each system at each timestep
q_history = ti.Vector.field(n_dof, dtype=ti.f32, shape=(steps, n_systems), needs_grad=True)

@ti.kernel
def initialize():
    for i in range(n_systems):
        q[i] = ti.Vector([0.1 * (i % 3), 0.1 * (i % 10), 0.1 * (i % 23), 0.1 * (i % 31)])
        q_dot[i] = ti.Vector([0.1 * (i % 10), 0.2, 0.3, 0.1])
        m[i] = 1.0 + i * 0.001
        ti.sync()



@ti.kernel
def simulate():
    # ti.loop_config(parallelize=1)  #Ensures sequential execution
    ti.loop_config(serialize=True)
    for i in range(n_systems):
        ti.loop_config(serialize=True)
        for t in range(steps):

            M[i] = ti.Matrix.identity(ti.f32, n_dof) * m[i]
            C[i] = ti.Matrix.zero(ti.f32, n_dof, n_dof)
            G[i] = ti.Vector([0.0, 0.0, 0.0, 0.0])
            tau[i] = -q[i]

            M_inv = M[i].inverse()
            q_ddot[i] = M_inv @ (tau[i] - C[i] @ q_dot[i] - G[i])

            new_q = q[i] + q_dot[i] * dt
            new_q_dot = q_dot[i] + q_ddot[i] * dt
            
            q_dot[i] = new_q_dot
            q[i] = new_q
            q_history[t, i] += q[i]  # Ensure correct storage
            ti.atomic_add(loss[None], q[i].norm_sqr())

# Main simulation with gradients
start_time = time.time()
initialize()

# Clear gradients and initialize loss
q.grad.fill(0)  # For debugging
q_dot.grad.fill(0)
m.grad.fill(0)
loss[None] = 0.0
loss.grad[None] = 1.0
q_history.fill(0)

q.grad.fill(0)  # For debugging

# Run forward and backward passes
simulate()
ti.sync()
simulate.grad()

# Retrieve results and gradients
q_np = q.to_numpy()
q_grad_np = q.grad.to_numpy()  # For debugging
q_dot_grad_np = q_dot.grad.to_numpy()
m_grad_np = m.grad.to_numpy()

# Convert trajectory history to numpy for plotting
q_history_np = q_history.to_numpy()




print("Final positions (first 5 systems):", q_np[:5])
# print("Final positions hist (first 5 systems):", q_history_np[-1,:5])
print("Gradient w.r.t. q (first 5 systems):", q_grad_np[:5])  # Debugging
print("Gradient w.r.t. initial q_dot (first 5 systems):", q_dot_grad_np[:5])
print("Gradient w.r.t. m (first 5 systems):", m_grad_np[:5])
print(f"Simulation took {time.time() - start_time:.2f}s")
print("Loss:", loss[None])

# print(q_history_np[:,0,0])

# Create plots for the first 10 systems
plt.figure(figsize=(10, 8))
for dof in range(n_dof):
    plt.subplot(2, 2, dof + 1)
    for system in range(10):
        plt.plot(np.arange(steps) * dt, q_history_np[:, system, dof], label=f'System {system}')
    plt.title(f'DOF {dof} Trajectory')
    plt.xlabel('Time (s)')
    plt.ylabel('Position')
    plt.legend()
plt.tight_layout()
plt.savefig(f'{this_dir}/trajectory2.png')
