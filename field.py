import numpy as np
from os import makedirs
from os.path import exists
from numbers import Number
import re

import config, parallel
from config import ad, T
from parallel import pprint
import BCs
from mesh import extractField, writeField

logger = config.Logger(__name__)

class Field(object):
    @staticmethod
    def setSolver(solver):
        Field.solver = solver
        mesh = solver.mesh
        Field.mesh = mesh
        if not hasattr(mesh, 'Normals'):
            mesh.Normals = Field('nF', mesh.normals, (3,))
            mesh.paddedMesh.Normals = Field('nF', mesh.paddedMesh.normals, (3,))

    def __init__(self, name, field, dimensions):
        self.name = name
        self.field = field
        self.dimensions = dimensions

    @classmethod
    def max(self, a, b):
        return self('max({0},{1})'.format(a.name, b.name), ad.maximum(a.field, b.field), a.dimensions)
    @classmethod
    def min(self, a, b):
        return self('min({0},{1})'.format(a.name, b.name), ad.minimum(a.field, b.field), a.dimensions)

    @classmethod
    def switch(self, condition, a, b):
        return self('switch({0},{1})'.format(a.name, b.name), ad.switch(condition, a.field, b.field), a.dimensions)


    def info(self):
        assert isinstance(self.field, np.ndarray)
        pprint(self.name + ':', end='')
        # mesh values required outside theano
        field = self.field[:self.mesh.origMesh.nLocalCells]
        fieldMin = parallel.min(field)
        fieldMax = parallel.max(field)
        assert not np.isnan(fieldMin)
        assert not np.isnan(fieldMax)
        pprint(' min:', fieldMin, 'max:', fieldMax)

    # creates a view
    def component(self, component): 
        assert self.dimensions == (3,)
        return self.__class__('{0}.{1}'.format(self.name, component), self.field[:,[0]], (1,))

    def magSqr(self):
        assert self.dimensions == (3,)
        if isinstance(self.field, np.ndarray):
            return self.__class__('magSqr({0})'.format(self.name), np.sum(self.field**2, axis=1, keepdims=True), (1,))
        else:
            return self.__class__('magSqr({0})'.format(self.name), ad.sum(self.field**2, axis=1, keepdims=True), (1,))

    def mag(self):
        return self.magSqr()**0.5

    def abs(self):
        return self.__class__('abs({0})'.format(self.name), ad.abs_(self.field), self.dimensions)

    def stabilise(self, num):
        return self.__class__('stabilise({0})'.format(self.name), ad.switch(ad.lt(self.field, 0.), self.field - num, self.field + num), self.dimensions)

    def sign(self):
        return self.__class__('abs({0})'.format(self.name), ad.sgn(self.field), self.dimensions)


    def dot(self, phi):
        assert self.dimensions[0] == 3
        # if tensor
        if len(self.dimensions) > 1:
            phi = self.__class__(phi.name, phi.field[:,np.newaxis,:], (1,3))
            dimensions = (3,)
        else:
            dimensions = (1,)
        product = ad.sum(self.field * phi.field, axis=-1)
        # if summed over vector
        if len(self.dimensions) == 1:
            product = product.reshape((self.field.shape[0],1))
        return self.__class__('dot({0},{1})'.format(self.name, phi.name), product, dimensions)

    def dotN(self):
        return self.dot(self.mesh.Normals)

    # represents self * phi
    def outer(self, phi):
        return self.__class__('outer({0},{1})'.format(self.name, phi.name), self.field[:,:,np.newaxis] * phi.field[:,np.newaxis,:], (3,3))
    
    # creates a view
    def transpose(self):
        assert len(self.dimensions) == 2
        return self.__class__('{0}.T'.format(self.name), self.field.transpose((0,2,1)), self.dimensions)

    def trace(self):
        assert len(self.dimensions) == 2
        phi = self.field
        return self.__class__('tr({0})'.format(self.name), (phi[:,0,0] + phi[:,1,1] + phi[:,2,2]).reshape((phi.shape[0],1)), (1,))

    def __neg__(self):
        return self.__class__('-{0}'.format(self.name), -self.field, self.dimensions)

    def __mul__(self, phi):
        if isinstance(phi, Number):
            return self.__class__('{0}*{1}'.format(self.name, phi), self.field * phi, self.dimensions)
        else:
            product = self.field * phi.field
            dimensions = max(self.dimensions, phi.dimensions)
            return self.__class__('{0}*{1}'.format(self.name, phi.name), self.field * phi.field, dimensions)


    def __rmul__(self, phi):
        return self * phi

    def __pow__(self, power):
        return self.__class__('{0}**{1}'.format(self.name, power), self.field.__pow__(power), self.dimensions)

    def __add__(self, phi):
        if isinstance(phi, Number):
            return self.__class__('{0}+{1}'.format(self.name, phi), self.field + phi, self.dimensions)
        else:
            return self.__class__('{0}+{1}'.format(self.name, phi.name), self.field + phi.field, self.dimensions)

    def __radd__(self, phi):
        return self.__add__(phi)

    def __sub__(self, phi):
        return self.__add__(-phi)

    def __div__(self, phi):
        return self.__class__('{0}/{1}'.format(self.name, phi.name), self.field / phi.field, self.dimensions)

class CellField(Field):
    def __init__(self, name, field, dimensions, boundary={}, ghost=False):
        logger.debug('initializing CellField {0}'.format(name))
        super(self.__class__, self).__init__(name, field, dimensions)
        mesh = self.mesh

        if len(list(boundary.keys())) == 0:
            self.boundary = mesh.defaultBoundary
        else:
            self.boundary = boundary

        # CellField does not contain processor patch data, but the size is still full = nCells in original code
        if ghost:
            # can be not filled
            self.resetField()

        self.BC = {}
        for patchID in self.mesh.origPatches:
            # skip processor patches
            patchType = self.boundary[patchID]['type']
            self.BC[patchID] = getattr(BCs, patchType)(self, patchID)

        if ghost:
            self.setInternalField(field)

    @classmethod
    def copy(self, phi):
        logger.info('copying field {0}'.format(phi.name))
        return self(phi.name, ad.array(ad.value(phi.field).copy()), phi.dimensions, phi.boundary.copy())

    @classmethod
    def getOrigField(self, phi):
        logger.info('getting original field {0}'.format(phi.name))
        if parallel.nProcessors == 1:
            return phi

        mesh = self.mesh.paddedMesh
        # every cell gets filled
        phiField = ad.bcalloc(config.precision(0.), ((self.mesh.nCells, ) + phi.dimensions))
        phiField = ad.set_subtensor(phiField[:self.mesh.nInternalCells], phi.field[:self.mesh.nInternalCells])
        phiField = ad.set_subtensor(phiField[self.mesh.nInternalCells:self.mesh.nLocalCells], phi.field[mesh.nInternalCells:self.mesh.nCells])
        phiField = ad.set_subtensor(phiField[self.mesh.nLocalCells:], phi.field[self.mesh.nInternalCells:mesh.nInternalCells])
        return self(phi.name, phiField, phi.dimensions, phi.boundary)

    def copyRemoteCells(self, internalField):
        # processor boundary condition completed by copying the extra data in internalField, HACK
        self.field = ad.set_subtensor(self.field[self.mesh.nLocalCells:], internalField[self.mesh.nInternalCells:])

    def resetField(self):
        mesh = self.mesh
        size = (mesh.nCells, ) + self.dimensions
        self.field = ad.bcalloc(config.precision(1.), size)
        #self.field.tag.test_value = np.zeros((mesh.origMesh.nCells,) + self.dimensions, config.precision)

    def setInternalField(self, internalField, reset=False):
        if reset:
            self.resetField()
        # boundary conditions complete cell field after setting internal field
        self.field = ad.set_subtensor(self.field[:self.mesh.nInternalCells], internalField[:self.mesh.nInternalCells])
        self.updateGhostCells()

    def getInternalField(self):
        return self.field[:self.mesh.nInternalCells]

    def updateGhostCells(self):
        logger.info('updating ghost cells for {0}'.format(self.name))
        for patchID in self.BC:
            self.BC[patchID].update()
    

class IOField(Field):
    def __init__(self, name, field, dimensions, boundary={}):
        super(self.__class__, self).__init__(name, field, dimensions)
        logger.debug('initializing IOField {0}'.format(name))
        self.boundary = boundary
        if len(list(boundary.keys())) == 0:
            self.boundary = self.mesh.defaultBoundary
        else:
            self.boundary = boundary
        self.func = None


    def complete(self, func=None):
        logger.debug('completing field {0}'.format(self.name))
        if func is None:
            X = ad.matrix()
            X.tag.test_value = self.field
            # CellField for later use
            self.phi = CellField(self.name, X, self.dimensions, self.boundary, ghost=True)
            Y = self.phi.field
            func = self.solver.function([X], Y)

        self.field = func(self.field)
        return func

    def getInternalField(self):
        return self.field[:self.mesh.origMesh.nInternalCells]

    @classmethod
    def read(self, name, mesh, time):
        # mesh values required outside theano
        if time.is_integer():
            time = int(time)
        pprint('reading field {0}, time {1}'.format(name, time))
        timeDir = '{0}/{1}/'.format(mesh.case, time)
        mesh = mesh.origMesh

        content = open(timeDir + name).read()
        foamFile = re.search(re.compile('FoamFile\n{(.*?)}\n', re.DOTALL), content).group(1)
        assert re.search('format[\s\t]+(.*?);', foamFile).group(1) == config.fileFormat
        vector = re.search('class[\s\t]+(.*?);', foamFile).group(1) == 'volVectorField'
        dimensions = 1 + vector*2
        bytesPerField = 8*(1 + 2*vector)
        startBoundary = content.find('boundaryField')
        data = re.search(re.compile('internalField[\s\r\n]+(.*)', re.DOTALL), content[:startBoundary]).group(1)
        internalField = extractField(data, mesh.nInternalCells, (dimensions,))
        content = content[startBoundary:]
        boundary = {}
        def getToken(x): 
            token = re.match('[\s\r\n\t]+([a-zA-Z0-9_\.\-\+<>\{\}]+)', x)
            return token.group(1), token.end()
        for patchID in mesh.boundary:
            patch = re.search(re.compile('[\s\r\n\t]+' + patchID + '[\s\r\n]+{', re.DOTALL), content)
            boundary[patchID] = {}
            start = patch.end()
            while 1:
                key, end = getToken(content[start:])
                start += end
                if key == '}':
                    break
                # skip non binary, non value, uniform or empty patches
                elif key == 'value' and config.fileFormat == 'binary' and getToken(content[start:])[0] != 'uniform' and mesh.boundary[patchID]['nFaces'] != 0:
                    match = re.search(re.compile('[ ]+(nonuniform[ ]+List<[a-z]+>[\s\r\n\t0-9]*\()', re.DOTALL), content[start:])
                    nBytes = bytesPerField * mesh.boundary[patchID]['nFaces']
                    start += match.end()
                    prefix = match.group(1)
                    boundary[patchID][key] = prefix + content[start:start+nBytes]
                    start += nBytes
                    match = re.search('\)[\s\r\n\t]*;', content[start:])
                    start += match.end()
                else:
                    match = re.search(re.compile('[ ]+(.*?);', re.DOTALL), content[start:])
                    start += match.end() 
                    boundary[patchID][key] = match.group(1)
        if vector:
            dimensions = (3,)
        else:
            dimensions = (1,)

        return self(name, internalField, dimensions, boundary)

    def write(self, time):
        # mesh values required outside theano
        name = self.name
        field = self.field
        boundary = self.boundary
        # fetch processor information
        parallel.getOrigRemoteCells(field, self.mesh)
        if time.is_integer():
            time = int(time)
        assert len(field.shape) == 2
        np.set_printoptions(precision=16)
        pprint('writing field {0}, time {1}'.format(name, time))
        timeDir = '{0}/{1}/'.format(self.mesh.case, time)
        if not exists(timeDir):
            makedirs(timeDir)
        handle = open(timeDir + name, 'w')
        handle.write(config.foamHeader)
        handle.write('FoamFile\n{\n')
        foamFile = config.foamFile.copy()
        foamFile['object'] = name
        if field.shape[1] == 3:
            dtype = 'vector'
            foamFile['class'] = 'volVectorField'
        else:
            dtype = 'scalar'
            foamFile['class'] = 'volScalarField'
        for key in foamFile:
            handle.write('\t' + key + ' ' + foamFile[key] + ';\n')
        handle.write('}\n')
        handle.write('// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n')
        handle.write('dimensions      [0 1 -1 0 0 0 0];\n')
        mesh = self.mesh.origMesh
        writeField(handle, field[:mesh.nInternalCells], dtype, 'internalField')
        handle.write('boundaryField\n{\n')
        for patchID in boundary:
            handle.write('\t' + patchID + '\n\t{\n')
            patch = boundary[patchID]
            if patch['type'] in config.valuePatches:
                patch.pop('value', None)
            for attr in patch:
                handle.write('\t\t' + attr + ' ' + patch[attr] + ';\n')
            if patch['type'] in config.valuePatches:
                startFace = mesh.boundary[patchID]['startFace']
                nFaces = mesh.boundary[patchID]['nFaces']
                endFace = startFace + nFaces
                cellStartFace = mesh.nInternalCells + startFace - mesh.nInternalFaces
                cellEndFace = mesh.nInternalCells + endFace - mesh.nInternalFaces
                writeField(handle, field[cellStartFace:cellEndFace], dtype, 'value')
            handle.write('\t}\n')
        handle.write('}\n')
        handle.close()


