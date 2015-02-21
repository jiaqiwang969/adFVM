from field import Field, CellField
import numpy as np

import config
from config import ad

logger = config.Logger(__name__)

def TVD_dual(phi, gradPhi):
    from op import grad
    assert len(phi.dimensions) == 1
    logger.info('TVD {0}'.format(phi.name))
    mesh = phi.mesh

    # every face gets filled
    faceField = ad.bcalloc(config.precision(0.), (mesh.nFaces, phi.dimensions[0]))
    faceFields = [faceField, faceField.copy()]
    # van leer
    psi = lambda r, rabs: (r + rabs)/(1 + rabs)
    def update(start, end):
        owner = mesh.owner[start:end]
        neighbour = mesh.neighbour[start:end]
        index = 0
        for C, D in [[owner, neighbour], [neighbour, owner]]:
            phiC = phi.field[C]
            phiD = phi.field[D]
            # wTF is *1 necessary over here for theano
            phiDC = (phiD-phiC)*1
            R = Field('R', ad.array(mesh.cellCentres[D] - mesh.cellCentres[C]), (3,))
            gradC = Field('gradC({0})'.format(phi.name), gradPhi.field[C], gradPhi.dimensions)
            gradF = Field('gradF({0})'.format(phi.name), phiDC, phi.dimensions)
            gradC = gradC.dot(R)
            if phi.dimensions[0] == 3:
                gradC = gradC.dot(gradF)
                gradF = gradF.magSqr()
            #r = 2.*gradC/gradF.stabilise(config.SMALL) - 1
            r = Field.switch(ad.gt(gradC.abs().field, 1000.*gradF.abs().field), 2.*1000.*gradC.sign()*gradF.sign() - 1., 2.*gradC/gradF.stabilise(config.VSMALL) - 1.)
            if phi.name == 'rhoE':
                phi.solver.local = gradF.field*1 + config.SMALL
                #phi.solver.local = r.field
                #phi.solver.remote = psi(r, r.abs()).field
                phi.solver.remote = gradF.stabilise(config.SMALL).field
            faceFields[index] = ad.set_subtensor(faceFields[index][start:end], phiC + 0.5*psi(r, r.abs()).field*phiDC)
            index += 1

    # internal, then local patches and finally remote
    update(0, mesh.nInternalFaces)
    for patchID in phi.boundary:
        startFace = mesh.boundary[patchID]['startFace']
        endFace = startFace + mesh.boundary[patchID]['nFaces']
        if phi.boundary[patchID]['type'] == 'coupled':
            update(startFace, endFace)
        else:
            for index in range(0, len(faceFields)):
                faceFields[index] = ad.set_subtensor(faceFields[index][startFace:endFace], phi.field[mesh.neighbour[startFace:endFace]])
    update(mesh.nFaces-(mesh.nCells-mesh.nLocalCells), mesh.nFaces)

    return [Field('{0}F'.format(phi.name), faceField, phi.dimensions) for faceField in faceFields]


def upwind(phi, U): 
    assert len(phi.dimensions) == 1
    logger.info('upwinding {0} using {1}'.format(phi.name, U.name)) 
    mesh = phi.mesh
    faceField = ad.bcalloc(config.precision(0.), (mesh.nFaces, phi.dimensions[0]))
    def update(start, end):
        positiveFlux = ad.value(ad.sum(U.field[start:end] * mesh.normals[start:end], axis=1)) > 0
        negativeFlux = 1 - positiveFlux
        faceField[positiveFlux] = phi.field[mesh.owner[positiveFlux]]
        faceField[negativeFlux] = phi.field[mesh.neighbour[negativeFlux]]

    update(0, mesh.nInternalFaces)
    for patchID in phi.boundary:
        startFace = mesh.boundary[patchID]['startFace']
        endFace = startFace + mesh.boundary[patchID]['nFaces']
        if phi.boundary[patchID]['type'] == 'coupled':
            update(startFace, endFace)
        else:
            faceField[startFace:endFace] = phi.field[mesh.neighbour[startFace:endFace]]
    update(mesh.nFaces-(mesh.nCells-mesh.nLocalCells), mesh.nFaces)

    return Field('{0}F'.format(phi.name), faceField, phi.dimensions)

def central(phi, mesh):
    logger.info('interpolating {0}'.format(phi.name))
    factor = mesh.weights
    # for tensor
    if len(phi.dimensions) == 2:
        factor = factor.reshape((factor.shape[0], 1, 1))
    faceField = Field('{0}F'.format(phi.name), phi.field[mesh.owner]*factor + phi.field[mesh.neighbour]*(1.-factor), phi.dimensions)
    # retain pattern broadcasting
    faceField.field = ad.patternbroadcast(faceField.field, phi.field.broadcastable)
    return faceField
