
import os, sys, subprocess, shutil
scriptDir = os.path.dirname(os.path.realpath(__file__))

from . import config
from .scalar import *
_dtype = dtype

class Variable(ArithBase):
#class Variable(object):
    _index = 0
    def __init__(self, shape, dtype=_dtype):
        index = Variable._index
        Variable._index += 1
        self.name = 'Variable_{}'.format(index)
        self.shape = shape
        self.args = ()
        self.index = 0
        self.dtype = dtype
        self.reference = None

    def __getitem__(self, index):
        var = self.getReference()
        var.index = index
        return var

    def getReference(self):
        var = Variable(self.shape)
        var.reference = self
        var.name = self.name
        return var

class TensorFunctionOp(object):
    def __init__(self, func, args, outputs, indices):
        self.func = func
        n = len(self.func._inputTensors)
        self.args = args
        self.outputs = outputs
        self.indices = indices
        for out in self.outputs:
            out.args = (self,)

class Function(object):
    _index = 0
    _module = None
    codeDir = os.path.dirname(__file__) + '/gencode/'

    def __init__(self, name, inputs, outputs):
        self.name = name
        self._inputs = inputs
        self._outputs = outputs
        self._genCode()

    def _genCode(self):
        codeFile = open(self.codeDir + 'code.cpp', 'a')
        memString = '' 
        for inp in self._inputs:
            memString += 'const {}* {}, '.format(inp.dtype, inp.name)
        for out in self._outputs:
            memString += '{}* {}, '.format(out.dtype, out.name)
        codeFile.write('\nvoid Function_{}({}) {}\n'.format(self.name, memString[:-2], '{\n'))

        codeFile.write('}')

        codeFile.close()

    @classmethod
    def createCodeDir(self, case):
        self.codeDir = case + 'gencode/'
        if config.compile:
            assert not os.path.exists(self.codeDir)
            shutil.copytree(scriptDir + '/gencode', self.codeDir)

    @classmethod
    def clean(self):
        #try:
        #    os.remove(self.codeDir + 'code.cpp')
        #except:
        #    pass
        with open(self.codeDir + 'code.cpp', 'a') as f:
            f.write('#include "code.hpp"\n')

    @classmethod
    def compile(self):
        if config.compile:
            with open(self.codeDir + 'code.cpp', 'a') as f:
                f.write('\n\n' + self.extraCode)
            subprocess.check_call(['make'], cwd=self.codeDir)
        parallel.mpi.Barrier()
        sys.path.append(self.codeDir)
        import interface as mod
        Function._module = mod

