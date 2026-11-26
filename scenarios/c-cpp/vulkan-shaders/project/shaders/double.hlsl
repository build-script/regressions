// the same as double.comp in HLSL, for dxc with the profile cs_6_0
RWStructuredBuffer<uint> values : register(u0, space0);

[numthreads(16, 1, 1)]
void main(uint3 id : SV_DispatchThreadID) {
    values[id.x] = values[id.x] * 2;
}
