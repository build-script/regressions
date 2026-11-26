// the same as double.comp in Slang, its stage by its attribute
RWStructuredBuffer<uint> values;

[shader("compute")]
[numthreads(16, 1, 1)]
void main(uint3 id : SV_DispatchThreadID) {
    values[id.x] = values[id.x] * 2;
}
