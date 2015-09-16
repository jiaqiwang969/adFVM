#!/usr/bin/python2
import config, parallel
from config import ad
from parallel import pprint

import numpy as np

from pyRCF import RCF
from field import IOField, CellField
from op import div, grad
from interp import central, TVD_dual

def computeFields(stackedFields, solver):
    mesh = solver.mesh
    paddedMesh = mesh.paddedMesh
    g = solver.gamma
    if hasattr(computeFields, 'computer'):
        return computeFields.computer(stackedFields)
    SF = ad.matrix()
    PSF = solver.padField(SF)
    pP, UP, TP = solver.unstackFields(PSF, CellField)
    cP = (g*TP*solver.R).sqrt()
    U = CellField.getOrigField(UP)
    T = CellField.getOrigField(TP)
    p = CellField.getOrigField(pP)
    c = cP.getOrigField(cP)

    #divU
    gradU = grad(central(UP, paddedMesh), ghost=True)
    ULF, URF = TVD_dual(U, gradU)
    UF = 0.5*(ULF + URF)
    divU = div(UF.dotN(), ghost=True)

    #speed of sound
    gradc = grad(central(cP, paddedMesh), ghost=True)
    gradp = grad(central(pP, paddedMesh), ghost=True)
    gradrho = g*(gradp-c*p)/(c*c)

    computeFields.computer = solver.function([SF], [gradrho.field, gradU.field, gradp.field, gradc.field, divU.field], 'compute')
    return computeFields.computer(stackedFields)

def getRhoaByV(rhoa):
    mesh = rhoa.mesh
    rhoaByV = np.zeros((mesh.origMesh.nCells, 1))
    nInternalCells = mesh.origMesh.nInternalCells
    rhoaByV[:nInternalCells] = rhoa.field[:nInternalCells]/mesh.origMesh.volumes
    rhoaByV = IOField('rhoaByV', rhoaByV, (1,), boundary=mesh.calculatedBoundary)
    return rhoaByV

def getAdjointEnergy(rhoa, rhoUa, rhoEa):
    adjEnergy = (rhoa.getInternalField()**2).sum(axis=1)
    adjEnergy += (rhoUa.getInternalField()**2).sum(axis=1)
    adjEnergy += (rhoEa.getInternalField()**2).sum(axis=1)
    adjEnergy = parallel.sum(adjEnergy)**0.5
    return adjEnergy

def getAdjointNorm(rho, rhoU, rhoE, U, T, p, *outputs):
    mesh = rho.mesh
    solver = rho.solver
    g = solver.gamma
    sg = np.sqrt(g)
    g1 = g-1
    sg1 = np.sqrt(g1)

    gradrho, gradU, gradp, gradc, divU = outputs
    rho = rho.field
    p = p.field
    c = np.sqrt(g*p/rho)
    b = c/sg
    a = sg1*c/sg
    gradb = gradc/sg
    grada = gradc*sg1/sg
    Z = np.zeros_like(divU)
    Z3 = np.zeros_like(gradU)
    np.hstack((divU, gradb, Z))
    np.hstack((gradb[:,[0]], divU, Z, Z, grada[:,[0]]))
    np.hstack((Z, grada, divU))
    M1 = np.dstack((np.hstack((divU, gradb, Z)),
               np.hstack((gradb[:,[0]], divU, Z, Z, grada[:,[0]])),
               np.hstack((gradb[:,[1]], Z, divU, Z, grada[:,[1]])),
               np.hstack((gradb[:,[2]], Z, Z, divU, grada[:,[2]])),
               np.hstack((Z, grada, divU))))

    M2 = np.dstack((np.hstack((Z, b*gradrho/rho, sg1*divU/2)),
                    np.hstack((np.dstack((Z,Z,Z)), gradU, (a*gradp/(2*p)).reshape(-1, 1, 3))),
                    np.hstack((Z, 2*grada/g1, g1*divU/2))))
    M1_2norm = np.ascontiguousarray(np.linalg.svd(M1, compute_uv=False)[:, [0]])
    M2_2norm = np.ascontiguousarray(np.linalg.svd(M2, compute_uv=False)[:, [0]])
    M_2norm = np.ascontiguousarray(np.linalg.svd(M1-M2, compute_uv=False)[:, [0]])
    M1_2norm = IOField('M1_2norm', M1_2norm, (1,), boundary=mesh.calculatedBoundary)
    M2_2norm = IOField('M2_2norm', M2_2norm, (1,), boundary=mesh.calculatedBoundary)
    M_2norm = IOField('M_2norm', M_2norm, (1,), boundary=mesh.calculatedBoundary)
    return M_2norm, M1_2norm, M2_2norm
 
if __name__ == "__main__":
    import time as timer
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('case')
    parser.add_argument('time', nargs='+', type=float)
    user = parser.parse_args(config.args)

    names = ['gradrho', 'gradU', 'gradp', 'gradc', 'divU']
    dimensions = [(3,), (3,3), (3,),(3,),(1,)]

    solver = RCF(user.case)
    mesh = solver.mesh

    for index, time in enumerate(user.time):
        pprint('Time:', time)
        start = timer.time()
        rho, rhoU, rhoE = solver.initFields(time)
        U, T, p = solver.U, solver.T, solver.p
        SF = solver.stackFields([p, U, T], np)
        outputs = computeFields(SF, solver)
        for field, name, dim in zip(outputs, names, dimensions):
            IO = IOField(name, field, dim)
            if len(dim) != 2:
                IO.write(time)
        pprint()

        # rhoaByV
        rhoa = IOField.read('rhoa', mesh, time)
        rhoaByV = getRhoaByV(rhoa)
        rhoaByV.write(time)
        pprint()

        ## adjoint energy
        rhoUa = IOField.read('rhoUa', mesh, time)
        rhoEa = IOField.read('rhoEa', mesh, time)
        adjEnergy = getAdjointEnergy(rhoa, rhoUa, rhoEa)
        pprint('L2 norm adjoint', time, adjEnergy)
        pprint()

        # adjoint blowup
        M_2norm, M1_2norm, M2_2norm = getAdjointNorm(rho, rhoU, rhoE, U, T, p, *outputs)
        M_2norm.write(time)
        M1_2norm.write(time)
        M2_2norm.write(time)
        end = timer.time()
        pprint('Time for computing: {0}'.format(end-start))

        pprint()
