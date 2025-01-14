#include <Kun/Context.hpp>
#include <Kun/LayoutMappers.hpp>
#include <Kun/Module.hpp>
#include <Kun/Ops.hpp>
#include <algorithm>
#include <cmath>
#include <vector>

namespace kun {
namespace ops {

template <typename INPUT, typename OUTPUT>
static void ScaleStocks(RuntimeStage *stage, size_t time_idx,
                       size_t __total_time, size_t __start, size_t __length) {
    auto num_stocks = stage->ctx->stock_count;
    auto &inbuf = stage->ctx->buffers[stage->stage->in_buffers[0]->id];
    auto in_num_time = inbuf.num_time;
    auto in_base_time = (in_num_time == __total_time) ? 0 : __start;
    float *input = inbuf.ptr;
    float *output = stage->ctx->buffers[stage->stage->out_buffers[0]->id].ptr;
    auto time_end =
        std::min(__start + (time_idx + 1) * time_stride, __start + __length);
    for (size_t t = __start + time_idx * time_stride; t < time_end; t++) {
        float sum = 0;
        for (size_t i = 0; i < num_stocks; i++) {
            float in = input[INPUT::call(i, t - in_base_time, in_num_time,
                                         num_stocks)];
            if (!std::isnan(in)) {
                sum += std::abs(in);
            }
        }
        for (size_t i = 0; i < num_stocks; i++) {
            float in = input[INPUT::call(i, t - in_base_time, in_num_time,
                                         num_stocks)];
            float out = (in==0 && sum==0)? NAN: (in / sum);
            output[OUTPUT::call(i, t - __start, __length, num_stocks)] = out;
        }
    }
}

void ScaleStocksST8s_ST8s(RuntimeStage *stage, size_t time_idx,
                         size_t __total_time, size_t __start, size_t __length) {
    ScaleStocks<MapperST8s, MapperST8s>(stage, time_idx, __total_time, __start,
                                       __length);
}

void ScaleStocksST8s_TS(RuntimeStage *stage, size_t time_idx,
                       size_t __total_time, size_t __start, size_t __length) {
    ScaleStocks<MapperST8s, MapperTS>(stage, time_idx, __total_time, __start,
                                     __length);
}

void ScaleStocksTS_TS(RuntimeStage *stage, size_t time_idx, size_t __total_time,
                     size_t __start, size_t __length) {
    ScaleStocks<MapperTS, MapperTS>(stage, time_idx, __total_time, __start,
                                   __length);
}

void ScaleStocksTS_ST8s(RuntimeStage *stage, size_t time_idx,
                       size_t __total_time, size_t __start, size_t __length) {
    ScaleStocks<MapperTS, MapperST8s>(stage, time_idx, __total_time, __start,
                                     __length);
}

} // namespace ops
} // namespace kun