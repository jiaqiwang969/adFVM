#ifndef COMMON_HPP
#define COMMON_HPP

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cmath>
#include <cassert>
#include <limits>
#include <iostream>
#include <iomanip>
#include <string>
#include <vector>
#include <tuple>
#include <map>
#include <typeinfo>

using namespace std;

//#define ADIFF 1#
//
#define STRING(s) #s
#define VALUE(x) STRING(x)
#define PRINT(var) #var "="  VALUE(var)

#if defined(GPU) || defined(CPU_FLOAT32)
    typedef float scalar;
#else
    typedef double scalar;
#endif
typedef int32_t integer;

#define NDIMS 4

struct memory {
    int usage;
    int maxUsage;
    map<string, void *> refs;
};
extern struct memory mem;

#ifdef _OPENMP
    #include <omp.h>
    //double __sync_fetch_and_add(scalar *operand, scalar incr) {
    //union {
    //    double   d;
    //    uint64_t i;
    //} oldval, newval, retval;
    //do {
    //    oldval.d = *(volatile double *)operand;
    //    newval.d = oldval.d + incr;
    //    __asm__ __volatile__ ("lock; cmpxchgq %1, (%2)"
    //      : "=a" (retval.i)
    //      : "r" (newval.i), "r" (operand),
    //       "0" (oldval.i)
    //      : "memory");
    //    } while (retval.i != oldval.i);
    //    return oldval.d;
    //}
#else
    #define omp_get_thread_num() 0
#endif


template <typename dtype, integer shape1=1, integer shape2=1, integer shape3=1>
class arrType {
    public:
    dtype type;
    dtype* data;
    //integer dims;
    integer shape;
    integer size;
    integer strides[NDIMS];
    bool ownData;
    bool staticVariable;

    void initPre() {
        this->shape = 0;
        for (integer i = 0; i < NDIMS; i++)  {
            this->strides[i] = 0;
        }
        this -> size = 0;
        this -> data = NULL;
        this -> ownData = false;
        this -> staticVariable = false;
    }

    void init(const integer shape) {
        this->initPre();
        this->shape = shape;
        //integer temp = 1;
        this->strides[3] = 1;
        this->strides[2] = shape3*this->strides[3];
        this->strides[1] = shape2*this->strides[2];
        this->strides[0] = shape1*this->strides[1];
        //cout << endl;
        this -> size = this->strides[0]*shape;
    }
    void destroy() {
        if (this->ownData && this->data != NULL) {
            this->dec_mem();
            delete[] this -> data; 
            this -> data = NULL;
        }
    }
    void inc_mem() {
        mem.usage += this->size*sizeof(dtype);
        if (mem.usage > mem.maxUsage) {
            mem.maxUsage = mem.usage;
        }
    }

    void dec_mem() {
        mem.usage -= this->size*sizeof(dtype);
    }

    arrType () {
        this->initPre();
    }

    arrType(const integer shape, bool zero=false) {
        this -> init(shape);
        this -> data = new dtype[this->size];
        this -> ownData = true;
        if (zero) 
            this -> zero();
        this->inc_mem();
    }

    arrType(const integer shape, dtype* data) {
        this -> init(shape);
        this -> data = data;
    }

    arrType(const integer shape, const dtype* data) {
        this->init(shape);
        this->data = const_cast<dtype *>(data);
    }

    arrType(const integer shape, const string& data) {
        this->init(shape);
        this->data = const_cast<dtype *>((dtype *)data.data());
    }

    // copy constructor?

    // move constructor
    arrType(arrType&& that) {
        //this->move(that);
        this->init(that.shape);
        this->data = that.data;
        this->ownData = that.ownData;
        that.ownData = false;
    }
    arrType& operator=(arrType&& that) {
        assert(this != &that);
        this->destroy();
        //this->move(that);
        this->init(that.shape);
        this->data = that.data;
        this->ownData = that.ownData;
        that.ownData = false;
        return *this;

    }
    ~arrType() {
        this->destroy();
    };
    
    const dtype& operator() (const integer i1) const {
        return const_cast<const dtype &>(data[i1*this->strides[0]]);
    }

    const dtype& operator() (const integer i1, const integer i2) const {
        return const_cast<const dtype &>(data[i1*this->strides[0] + 
                      i2*this->strides[1]]);
    }
    const dtype& operator() (const integer i1, const integer i2, const integer i3) const {
        return const_cast<const dtype &>(data[i1*this->strides[0] + 
                      i2*this->strides[1] +
                      i3*this->strides[2]]);
    }



    dtype& operator()(const integer i1) {
        return const_cast<dtype &>(static_cast<const arrType &>(*this)(i1));
    }
    dtype& operator()(const integer i1, const integer i2) {
        return const_cast<dtype &>(static_cast<const arrType &>(*this)(i1, i2));
    }
    dtype& operator()(const integer i1, const integer i2, const integer i3) {
        return const_cast<dtype &>(static_cast<const arrType &>(*this)(i1, i2, i3));
    }

    void zero() {
        memset(this->data, 0, this->size*sizeof(dtype));
    }

    void copy(const integer index, const dtype* sdata, const integer n) {
        memcpy(&(*this)(index), sdata, n*sizeof(dtype));
    }
    void extract(const integer index, const integer* indices, const dtype* phiBuf, const integer n) {
        integer i, j, k;
        #pragma omp parallel for private(i, j, k)
        for (i = 0; i < n; i++) {
            integer p = indices[i];
            integer b = index + i;
            for (j = 0; j < shape1; j++) {
                for (k = 0; k < shape2; k++) {
                    (*this)(b, j, k) += phiBuf[p*shape1*shape2 + j*shape2 + k];
                }
            }
        }
    }
    void extract(const integer *indices, const dtype* phiBuf, const integer n) {
        integer i, j, k;
        #pragma omp parallel for private(i, j, k)
        for (i = 0; i < n; i++) {
            integer p = indices[i];
            for (j = 0; j < shape1; j++) {
                for (k = 0; k < shape2; k++) {
                    #pragma omp atomic 
                    (*this)(p, j, k) += phiBuf[i*shape1*shape2 + j*shape2 + k];
                    //__sync_fetch_and_add(&(*this)(p, j, k), phiBuf[i*shape1*shape2 + j*shape2 + k]);
                }
            }
        }
    }
    // not used by default
    bool checkNAN() {
        for (integer i = 0; i < this->size; i++) {
            if (std::isnan(this->data[i])) {
                return true;
            }
        }
        return false;
    }
    void info(int s=0, int e=-1) const {
        cout << setprecision(15) << this->sum(s, e) << endl;
        return;

        scalar minPhi, maxPhi;
        minPhi = 1e100;
        maxPhi = -1e100;
        integer minLoc = -1, maxLoc = -1;
        for (integer i = 0; i < this->size; i++) {
            if (this->data[i] < minPhi) {
                minPhi = this->data[i];
                minLoc = i;
            }
            if (this->data[i] > maxPhi) {
                maxPhi = this->data[i];
                maxLoc = i;
            }

        }
        cout << "phi min/max:" << minPhi << " " << maxPhi << endl;
        //cout << "loc min/max:" << minLoc << " " << maxLoc << endl;
    } 
    dtype sum(int s=0,int  e=-1) const {
        dtype res = 0;
        if (e == -1) {
            e = this->shape;
        }
        for (integer i = s; i < e; i++) {
            for (integer j = 0; j < shape1; j++) {
                for (integer k = 0; k < shape2; k++) {
                    res += (*this)(i, j, k);
                }
            }
        }
        return res;
    }

};

#ifndef GPU
    #define extArrType arrType
    typedef extArrType<scalar, 1> ext_vec;
#endif

typedef arrType<scalar> vec;
typedef arrType<scalar, 3> mat;
typedef arrType<integer> ivec;
typedef arrType<integer, 3> imat;

#endif
