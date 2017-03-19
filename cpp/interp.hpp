#ifndef INTERP_HPP
#define INTERP_HPP

#include "interface.hpp"

class Interpolator {
    Mesh const* mesh;
    
    public:
        Interpolator(Mesh const* mesh): mesh(mesh) {};
        void central(const arr&, scalar [], integer);
        void secondOrder(const arr& phi, const arr& gradPhi, scalar *phiF, integer index, integer which);
};
 

#endif
