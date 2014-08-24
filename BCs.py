from __future__ import print_function
import numpy as np
import numpad as ad

import utils
logger = utils.logger(__name__)

class BoundaryCondition(object):
    def __init__(self, phi, patchID):
        logger.info('initializating boundary condition for {0}'.format(patchID))
        self.patch = phi.boundary[patchID]
        self.patchID = patchID
        self.mesh = phi.mesh
        self.field = phi.field
        self.startFace = self.mesh.boundary[patchID]['startFace']
        self.nFaces = self.mesh.boundary[patchID]['nFaces']
        self.endFace = self.startFace + self.nFaces
        self.cellStartFace = self.mesh.nInternalCells + self.startFace - self.mesh.nInternalFaces
        self.cellEndFace = self.mesh.nInternalCells + self.endFace - self.mesh.nInternalFaces
        self.internalIndices = self.mesh.owner[self.startFace:self.endFace]

class cyclic(BoundaryCondition):
    def __init__(self, field, patchID):
        super(self.__class__, self).__init__(field, patchID)
        neighbourPatch = self.mesh.boundary[patchID]['neighbourPatch']
        neighbourStartFace = self.mesh.boundary[neighbourPatch]['startFace']
        neighbourEndFace = neighbourStartFace + self.nFaces
        self.neighbourIndices = self.mesh.owner[neighbourStartFace:neighbourEndFace]

    def update(self):
        logger.debug('cyclic BC for {0}'.format(self.patchID))
        self.field[self.cellStartFace:self.cellEndFace] = self.field[self.neighbourIndices]

class processor(BoundaryCondition):
    def __init__(self, field, patchID):
        super(self.__class__, self).__init__(field, patchID)
        self.local = self.mesh.boundary[patchID]['myProcNo']
        self.remote = self.mesh.boundary[patchID]['neighbProcNo']
        self.recvIndices = range(self.cellStartFace, self.cellEndFace)

    def update(self, exchanger):
        logger.debug('processor BC for {0}'.format(self.patchID))
        exchanger.exchange(self.remote, self.internalIndices, self.recvIndices)

class zeroGradient(BoundaryCondition):
    def update(self):
        logger.debug('zeroGradient BC for {0}'.format(self.patchID))
        self.field[self.cellStartFace:self.cellEndFace] = self.field[self.internalIndices]

class symmetryPlane(zeroGradient):
    def update(self):
        logger.debug('symmetryPlane BC for {0}'.format(self.patchID))
        super(self.__class__, self).update()
        # if vector
        if self.field.shape[1:] == (3,):
            v = -self.mesh.normals[self.startFace:self.endFace]
            self.field[self.cellStartFace:self.cellEndFace] -= ad.sum(self.field[self.cellStartFace:self.cellEndFace]*v, axis=1).reshape((-1,1))*v

class fixedValue(BoundaryCondition):
    def __init__(self, field, patchID):
        super(self.__class__, self).__init__(field, patchID)
        self.value = utils.extractField(self.patch['value'], self.nFaces, self.field.shape == 3)

    def update(self):
        logger.debug('fixedValue BC for {0}'.format(self.patchID))
        self.field[self.cellStartFace:self.cellEndFace] = self.value

slip = symmetryPlane
empty = zeroGradient
inletOutlet = zeroGradient
    

