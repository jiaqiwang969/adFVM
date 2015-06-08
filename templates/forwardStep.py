from pyRCF import RCF 
import config
from config import ad
import numpy as np
primal = RCF('cases/forwardStep/', timeIntegrator='euler', CFL=0.7, Cp=2.5, mu=lambda T: config.VSMALL*T)

def objective(fields, mesh):
    rho, rhoU, rhoE = fields
    patchID = 'obstacle'
    startFace = mesh.boundary[patchID]['startFace']
    endFace = startFace + mesh.boundary[patchID]['nFaces']
    cellStartFace = mesh.nInternalCells + startFace - mesh.nInternalFaces
    cellEndFace = mesh.nInternalCells + endFace - mesh.nInternalFaces
    areas = mesh.areas[startFace:endFace]
    field = rhoE.field[cellStartFace:cellEndFace]
    return ad.sum(field*areas)

def perturb(stackedFields, mesh, t):
    patchID = 'inlet'
    startFace = mesh.boundary[patchID]['startFace']
    endFace = startFace + mesh.boundary[patchID]['nFaces']
    cellStartFace = mesh.nInternalCells + startFace - mesh.nInternalFaces
    cellEndFace = mesh.nInternalCells + endFace - mesh.nInternalFaces
    stackedFields[cellStartFace:cellEndFace][:,1] += 0.1

nSteps = 10
writeInterval = 2
startTime = 0.0
dt = 1e-9

