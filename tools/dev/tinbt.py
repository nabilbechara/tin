"""lldb helper: `tinbt` walks the frame-pointer chain of a stopped Tin binary."""
import lldb

def tinbt(debugger, command, result, internal_dict):
    t = debugger.GetSelectedTarget()
    p = t.GetProcess()
    fr = p.GetSelectedThread().GetFrameAtIndex(0)
    err = lldb.SBError()
    def name(a):
        s = t.ResolveLoadAddress(a).GetSymbol()
        off = a - s.GetStartAddress().GetLoadAddress(t) if s.IsValid() else 0
        return "%s+%d" % (s.GetName(), off)
    pc = fr.GetPC()
    out = []
    out.append("pc   " + name(pc))
    out.append("lr   " + name(fr.FindRegister("lr").GetValueAsUnsigned()))
    regs = " ".join("x%d=%#x" % (i, fr.FindRegister("x%d" % i).GetValueAsUnsigned()) for i in range(0, 4))
    out.append("     " + regs)
    fp = fr.FindRegister("fp").GetValueAsUnsigned()
    for i in range(int(command or "25")):
        if fp == 0:
            break
        nfp = p.ReadPointerFromMemory(fp, err)
        ra = p.ReadPointerFromMemory(fp + 8, err)
        if not err.Success():
            break
        out.append("%2d  %s" % (i, name(ra)))
        fp = nfp
    result.AppendMessage("\n".join(out))

def __lldb_init_module(debugger, internal_dict):
    debugger.HandleCommand("command script add -f tinbt.tinbt tinbt")
    debugger.HandleCommand("command script add -f tinbt.tinnode tinnode")

def tinnode(debugger, command, result, internal_dict):
    """tinnode: dump the AST node the caller frame holds in x19 (saved at [fp+16])."""
    t = debugger.GetSelectedTarget()
    p = t.GetProcess()
    fr = p.GetSelectedThread().GetFrameAtIndex(0)
    err = lldb.SBError()
    fp = fr.FindRegister("fp").GetValueAsUnsigned()
    depth = int(command or "1")
    for _ in range(depth - 1):
        fp = p.ReadPointerFromMemory(fp, err)
    node = p.ReadPointerFromMemory(fp + 16, err)
    out = ["node %#x" % node]
    for i in range(8):
        w = p.ReadPointerFromMemory(node + 8 * i, err)
        s = ""
        if 0x100000000 < w < 0x800000000000:
            b = p.ReadMemory(w, 16, err)
            if err.Success():
                s = repr(b.split(b"\0")[0][:16])
        out.append("  [%d] %#x %s" % (i, w, s))
    result.AppendMessage("\n".join(out))

def __lldb_init_module2(debugger):
    debugger.HandleCommand("command script add -f tinbt.tinnode tinnode")
