from KunQuant.ops.MiscOp import BackRef
from KunQuant.ops.ElewiseOp import AddConst, DivConst, Sqrt, Sub, Log, Div, CmpOp, Mul, Sign
from KunQuant.passes.Util import kun_pass
from KunQuant.Op import Builder, OpBase, ForeachBackWindow, Rank, WindowedTempOutput, Output, IterValue, ConstantOp, Scale
from KunQuant.ops import ReduceAdd, FastWindowedSum, SubConst, MulConst
from KunQuant.Stage import Function
from typing import List, Dict, Tuple

def _is_ok_for_reduce_opt(op: OpBase, enabled: bool) -> Tuple[OpBase, int]:
    if not enabled:
        return None
    if not isinstance(op, ReduceAdd):
        return None
    if op.get_parent() is not None:
        return None
    itr = op.inputs[0]
    if not isinstance(itr, IterValue):
        return None
    loop = itr.inputs[0]
    window_data = itr.inputs[1]
    if not isinstance(loop, ForeachBackWindow):
        return None
    window = loop.attrs["window"]
    return window_data, window

def _is_sub_log(op: OpBase) -> OpBase:
    '''
    if the op matches sub(log(X), log(Y)) or sub(log(X), backref(log(Y)))
    '''
    if not isinstance(op, Sub):
        return None
    lhs = op.inputs[0]
    rhs = op.inputs[1]
    if not isinstance(lhs, Log):
        return None
    if isinstance(rhs, Log):
        t = Div(lhs.inputs[0], rhs.inputs[0])
        return Log(t)
    elif isinstance(rhs, BackRef) and isinstance(rhs.inputs[0], WindowedTempOutput) and isinstance(rhs.inputs[0].inputs[0], Log):
        windowop = rhs.inputs[0]
        internal = rhs.inputs[0].inputs[0].inputs[0]
        newtemp_window = WindowedTempOutput(internal, windowop.attrs["window"])
        newbackref = BackRef(newtemp_window, rhs.attrs["window"])
        ret = Log(Div(lhs.inputs[0], newbackref))
        return ret
    return None

def _is_const_1(op: OpBase) -> bool:
    return isinstance(op, ConstantOp) and op.attrs["value"] == 1

def _is_mul_1(op: OpBase) -> OpBase:
    if isinstance(op, MulConst) and op.attrs["value"] == -1:
        return SubConst(op.inputs[0], 0, True)
    if isinstance(op, Mul):
        if _is_const_1(op.inputs[0]):
            return op.inputs[1]
        if _is_const_1(op.inputs[1]):
            return op.inputs[0]
    return None

def _is_div_cmp_1(op: OpBase) -> OpBase:
    if isinstance(op, CmpOp):
        lhs, rhs = op.inputs
        if isinstance(lhs, Div):
            inner_lhs, inner_rhs = lhs.inputs
            if _is_const_1(rhs):
                return op.__class__(inner_lhs, inner_rhs)
            else:
                return op.__class__(inner_lhs, inner_rhs * rhs)
        if isinstance(rhs, Div):
            inner_lhs, inner_rhs = rhs.inputs
            if _is_const_1(lhs):
                return op.__class__(inner_rhs, inner_lhs)
            else:
                return op.__class__(lhs * inner_rhs, inner_lhs)
    return None

_monotonic_ops = {Sqrt, Log, Scale, Rank}
_monotonic_add = {AddConst, MulConst}
_monotonic_sub = {SubConst, DivConst}
def _is_rank_monotonic_inc(op: OpBase) -> OpBase:
    '''
    check if is Rank(T(x)) where T is monotonicly increasing
    '''
    if not isinstance(op, Rank):
        return None
    internal = op.inputs[0]
    if internal.__class__ in _monotonic_ops:
        return Rank(internal.inputs[0])
    if internal.__class__ in _monotonic_sub and not internal.attrs.get("swap") and internal.attrs["value"] > 0:
        return Rank(internal.inputs[0])
    if internal.__class__ in _monotonic_add and internal.attrs["value"] > 0:
        return Rank(internal.inputs[0])
    return None

def _is_sign_scale(op: OpBase) -> OpBase:
    '''
    check if is Sign(T(x)) where T does not change the signness of x
    '''
    if not isinstance(op, Sign):
        return None
    internal = op.inputs[0]
    if isinstance(internal, Scale):
        return Sign(internal.inputs[0])
    if isinstance(internal, MulConst) and internal.attrs["value"] > 0:
        return Sign(internal.inputs[0])
    if isinstance(internal, DivConst) and internal.attrs["value"] > 0 and not internal.attrs.get("swap"):
        return Sign(internal.inputs[0])
    return None

def special_impl(ops: List[OpBase], options: dict = {}) -> List[OpBase]:
    replace_map = dict()
    out = []
    changed = False
    def _transform(f, op) -> bool:
        nonlocal changed, replace_map, out
        b = Builder(op.get_parent())
        with b:
            newop = f(op)
        if newop is not None:
            if b.ops:
                out.extend(b.ops)
                if newop != b.ops[-1]:
                    out.append(newop)
            else:
                out.append(newop)
            changed = True
            replace_map[op] = newop
            return True
        return False
    for op in ops:
        op.replace_inputs(replace_map)
        if _transform(_is_mul_1, op):
            continue
        if _transform(_is_sub_log, op):
            continue
        if _transform(_is_rank_monotonic_inc, op):
            continue
        if _transform(_is_div_cmp_1, op):
            continue
        if _transform(_is_sign_scale, op):
            continue
        
        # if it is reduce-sum in non-loop context
        result = _is_ok_for_reduce_opt(op, options.get("opt_reduce", True))
        if result is None:
            out.append(op)
            continue
        opt_in, window = result
        newop = FastWindowedSum(opt_in, window)
        # FastWindowedSum needs an additional window size than original Sum
        if isinstance(opt_in, WindowedTempOutput):
            assert(opt_in.attrs["window"] >= window)
            if opt_in.attrs["window"] < window + 1:
                opt_in.attrs["window"] = window + 1
        out.append(newop)
        changed = True    
        replace_map[op] = newop
    if changed:
        return out
    return None

@kun_pass
def special_optimize(f: Function, options: dict = {}):
    '''
    Optimize:
    y = ...
    x = WindowedTempOutput(y) or Output(y)
    x2 = ForeachBackWindow(x)
    x3 = ReduceAdd(x2)
    =======================
    Into
    x3 = FastWindowedSum(y)

    And Mul(-1) => Sub(0, X)
    Rank(T(x)) where T is monotonicly increasing => Rank(x)
    sub(log(X), log(Y)) or sub(log(X), backref(log(Y))) => change to log(div(...))
    '''
    while True:
        newops = special_impl(f.ops, options)
        if newops is not None:
            newops = Function.topo_sort_ops(newops)
            f.set_ops(newops)
        else:
            break