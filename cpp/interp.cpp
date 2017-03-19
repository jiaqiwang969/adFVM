#include "interp.hpp"

void Interpolator::central(const arr& phi, scalar* phiF, integer index) {
    const Mesh& mesh = *this->mesh;
    integer p = mesh.owner(index);
    integer n = mesh.neighbour(index);
    integer w = mesh.weights(index);
    for (integer i = 0; i < phi.shape[1]; i++) {
        phiF[i] = phi(index, n)*(1-w) + phi(index, p)*w;
    }
}

void Interpolator::secondOrder(const arr& phi, const arr& gradPhi, scalar *phiF, integer index, integer swap) {
    const Mesh& mesh = *this->mesh;
    integer p, n;
    if (swap) {
        n = mesh.owner(index);
        p = mesh.neighbour(index);
    } else {
        p = mesh.owner(index);
        n = mesh.neighbour(index);
    }
    for (integer i = 0; i < phi.shape[1]; i++) {
        scalar phiC = phi(p, i);
        scalar phiD = phi(n, i);
        phiF[i] = phiC + (phiD-phiC)*mesh.linearWeights(swap, index);
        for (integer j = 0; j < 3; j++) {
            phiF[i] += mesh.quadraticWeights(swap, index, j)*gradPhi(index, j);
        }
    }
}
