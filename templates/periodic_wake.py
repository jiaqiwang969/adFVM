import numpy as np

from adFVM import config
from adFVM.config import ad
from adFVM.compat import norm
from adFVM.density import RCF 

primal = RCF('/home/talnikar/adFVM/cases/periodic_wake/')#, timeIntegrator='euler')

def objective(fields, mesh):
    res = fields[0].field.sum()
    return res

def source(fields, mesh, t):
    mesh = mesh.origMesh
    n = mesh.nInternalCells
    U = fields[1].field[:n]/fields[0].field[:n]
    x = mesh.cellCentres[:n, 0]
    y = mesh.cellCentres[:n, 1]
    rho = np.zeros((n, 1))
    rhoE = np.zeros((n, 1))

    def blasius(x):
        a = 0.33
        m = 4.2
        c = a*x
        b = (c**m/(1+c**m))**(1/m)
        return b

    lx = 0.03
    ly = 0.02
    mid = ly/2
    dw = 0.001
    Bx = (0.003, 0.027)
    wy = (mid-dw/2, mid+dw/2)
    ux = 100

    B = np.zeros_like(x)
    left = x <= Bx[0]
    right = x >= Bx[1]
    B[left] = np.exp(-1/(1-(x[left]/Bx[0])**2))
    B[right] = np.exp(-1/(1-((x[right]-lx)/(lx-Bx[1]))**2))
    B = B.reshape((-1,1))

    down = y <= wy[0]
    up = y >= wy[1]
    w = np.zeros_like(U)
    w[:, 0] = ux
    w[down, 0] = ux*(1+blasius(100*(wy[0]-y[down])/wy[0]))
    w[up, 0] = ux*(1+blasius(100*(y[up]-wy[1])/(ly-wy[1])))

    rhoU = 1e4*B*(w-U)

    return rho, rhoU, rhoE

#Steps = 20000
#riteInterval = 500
nSteps = 200000
writeInterval = 5000
startTime = 0.0
dt = 1e-7
