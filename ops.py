from __future__ import print_function
import numpy as np
import numpad as ad
import time

from field import Field
import utils
logger = utils.logger(__name__)

def TVD_dual(phi):
    logger.info('TVD {0}'.format(phi.name))
    mesh = phi.mesh
    # van leer
    psi = lambda r: (r + r.abs())/(1 + r.abs())
    SMALL = 1e-16

    faceFields = []
    # restructure, cyclic boundaries?
    gradField = grad(interpolate(phi))
    owner = mesh.owner[:mesh.nInternalFaces]
    neighbour = mesh.neighbour[:mesh.nInternalFaces]
    for C, D in [[owner, neighbour], [neighbour, owner]]:
        R = Field('R', mesh, mesh.cellCentres[D] - mesh.cellCentres[C])
        gradC = Field('gradC({0})'.format(phi.name), mesh, gradField.field[C])
        gradF = Field('gradF({0})'.format(phi.name), mesh, phi.field[D]-phi.field[C])
        if phi.field.shape[1] == 1:
            r = 2*gradC.dot(R)/(gradF + SMALL) - 1
        else:
            R.field = R.field[:,np.newaxis,:]
            r = 2*gradC.dot(R).dot(gradF)/(gradF.magSqr() + SMALL) - 1
        faceFields.append(Field(phi.name + 'F', mesh, ad.zeros((mesh.nFaces, phi.field.shape[1]))))
        faceFields[-1].field[:mesh.nInternalFaces] = phi.field[C] + 0.5*psi(r).field*(phi.field[D] - phi.field[C])

        for patchID in phi.boundary:
            if phi.boundary[patchID]['type'] != 'cyclic':
                startFace = mesh.boundary[patchID]['startFace']
                endFace = startFace + mesh.boundary[patchID]['nFaces']
                faceFields[-1].field[startFace:endFace] = phi.field[mesh.neighbour[startFace:endFace]]

    return faceFields

def upwind(phi, U): 
    logger.info('upwinding {0} using {1}'.format(phi.name, U.name)) 
    mesh = phi.mesh
    faceField = ad.zeros((mesh.nFaces, phi.field.shape[1]))
    def update(start, end):
        positiveFlux = ad.value(ad.sum(U.field[start:end] * mesh.normals[start:end], axis=1)) > 0
        negativeFlux = 1 - positiveFlux
        faceField[positiveFlux] = phi.field[mesh.owner[positiveFlux]]
        faceField[negativeFlux] = phi.field[mesh.neighbour[negativeFlux]]

    update(0, mesh.nInternalFaces)
    for patchID in phi.boundary:
        startFace = mesh.boundary[patchID]['startFace']
        endFace = startFace + mesh.boundary[patchID]['nFaces']
        if phi.boundary[patchID]['type'] != 'cyclic':
            faceField[startFace:endFace] = phi.field[mesh.neighbour[startFace:endFace]]
        else:
            update(startFace, endFace)

    return Field('{0}F'.format(phi.name), mesh, faceField)

def interpolate(phi):
    logger.info('interpolating {0}'.format(phi.name))
    mesh = phi.mesh
    factor = (mesh.faceDeltas/mesh.deltas)
    faceField = Field('{0}F'.format(phi.name), mesh, phi.field[mesh.owner]*factor + phi.field[mesh.neighbour]*(1-factor))
    return faceField

def div(phi, U=None):
    logger.info('divergence of {0}'.format(phi.name))
    mesh = phi.mesh
    if U is None:
        divField = (mesh.sumOp * (phi.field * mesh.areas))/mesh.volumes
    else:
        divField = (mesh.sumOp * ((field * U).dotN().field * mesh.areas))/mesh.volumes
    return Field('div({0})'.format(phi.name), mesh, divField)

def grad(phi):
    logger.info('gradient of {0}'.format(phi.name))
    mesh = phi.mesh
    normals = Field('n', mesh, mesh.normals)
    gradField = (mesh.sumOp * (phi.outer(normals).field * mesh.areas[:,:,np.newaxis]))/mesh.volumes[:,:,np.newaxis]
    if gradField.shape[1] == 1:
        gradField = gradField.reshape((gradField.shape[0], gradField.shape[2]))
    return Field('grad({0})'.format(phi.name), mesh, gradField)

def laplacian(phi, DT):
    logger.info('laplacian of {0}'.format(phi.name))
    mesh = phi.mesh

    # non orthogonal correction
    #DTgradF = Field.zeros('grad' + phi.name, mesh, mesh.nCells, 3.)
    #DTgradF.setInternalField(DT*grad(field))
    #laplacian1 = div(interpolate(DTgradF), 1.)

    gradFdotn = (phi.field[mesh.neighbour]-phi.field[mesh.owner])/mesh.deltas
    laplacian2 = (mesh.sumOp * (DT * gradFdotn * mesh.areas))/mesh.volumes
    return Field('laplacian' + phi.name, mesh, laplacian2)

def ddt(phi, phi0, dt):
    logger.info('ddt of {0}'.format(phi.name))
    return Field('ddt' + phi.name, phi.mesh, (phi.getInternalField()-ad.value(phi0.getInternalField()))/dt)

def explicit(equation, boundary, fields, dt):
    names = [phi.name for phi in fields]
    print('Time marching for', ' '.join(names))
    for index in range(0, len(fields)):
        fields[index].info()
     
    start = time.time()
    
    LHS = equation(*fields)
    internalFields = [(fields[index].getInternalField() - LHS[index].field*dt) for index in range(0, len(fields))]
    boundary(*internalFields)

    end = time.time()
    print('Time for iteration:', end-start)
 

def implicit(equation, boundary, fields):
    names = [phi.name for phi in fields]
    print('Solving for', ' '.join(names))
    for index in range(0, len(fields)):
        fields[index].info()

    start = time.time()

    nDims = [phi.field.shape[1] for phi in fields]
    def setInternalFields(stackedInternalFields):
        curr = 0
        internalFields = []
        for index in range(0, len(fields)):
            internalFields.append(stackedInternalFields[:,curr:curr+nDims[index]])
            curr += nDims[index]
        boundary(*internalFields)

    def solver(internalFields):
        setInternalFields(internalFields)
        equationFields = [phi.field for phi in equation(*fields)]
        return ad.hstack(equationFields)

    stack = [phi.getInternalField() for phi in fields]
    solution = ad.solve(solver, ad.hstack(stack))
    setInternalFields(solution)

    end = time.time()
    print('Time for iteration:', end-start)

def forget(fields):
    logger.info('forgetting fields')
    for phi in fields:
        phi.field.obliviate()

