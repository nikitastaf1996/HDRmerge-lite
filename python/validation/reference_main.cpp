// Test harness for the unmodified HDRMerge processing sources; GPL-3.0-or-later.
#include <iostream>
#include <fstream>
#include <vector>
#include "ImageStack.hpp"
#include "RawParameters.hpp"
#include "Log.hpp"
using namespace hdrmerge;
RawParameters::RawParameters() : width(0),height(0),rawWidth(0),rawHeight(0),topMargin(0),leftMargin(0),max(0),black(0),maxBlack(0),cblack{},preMul{},camMul{},camXyz{},rgbCam{},isoSpeed(0),shutter(0),aperture(0),colors(0){}
int main(int argc, char **argv) {
 if(argc!=10) return 1;
 size_t w=atoi(argv[1]),h=atoi(argv[2]);
 RawParameters p; p.width=p.rawWidth=w; p.height=p.rawHeight=h; p.max=1023; p.black=64;p.maxBlack=64;p.colors=3;
 for(int i=0;i<4;i++)p.cblack[i]=64;
 // RGGB filters: LibRaw RGGB = 0xb4b4b4b4: R G G2 B.
 p.FC.setPattern(0xb4b4b4b4,{});
 p.camMul[0]=atof(argv[6]);p.camMul[1]=atof(argv[7]);p.camMul[2]=atof(argv[8]);p.camMul[3]=p.camMul[1];
 Log::setMinimumPriority(0); Log::setOutputStream(std::cout);
 ImageStack stack;
 for(int i=3;i<6;i++) {std::vector<uint16_t> raw(w*h); std::ifstream f(argv[i],std::ios::binary); f.read((char*)raw.data(),raw.size()*2); if(!f) return 2; stack.addImage(Image(raw.data(),p,QString(argv[i])));}
 stack.calculateSaturationLevel(p); if(!getenv("NOALIGN")) { stack.align(); stack.crop(); } stack.computeResponseFunctions(); stack.generateMask();
 p.width=stack.getWidth(); p.height=stack.getHeight();
 std::cout << "crop " << p.width << " " << p.height << "\n";
 for(int i=0;i<3;i++) std::cout << "shift " << stack.getImage(i).getDeltaY() << " " << stack.getImage(i).getDeltaX() << " slope " << stack.getImage(i).getRelativeExposure() << "\n";
 auto result=stack.compose(p,3); std::ofstream o(argv[9],std::ios::binary);o.write((char*)result.begin(),result.size()*4);
}
