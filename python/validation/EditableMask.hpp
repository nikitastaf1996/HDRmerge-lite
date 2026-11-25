#pragma once
#include "Array2D.hpp"
namespace hdrmerge {class EditableMask: public Array2D<uint8_t>{public: void reset(){}; virtual ~EditableMask(){}; private: virtual bool isLayerValidAt(int,int,int) const=0;};}
