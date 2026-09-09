"""Reassign known supplied quantities before dispatch, without discarding purchases.

Continuous, unrestricted supplier-carrier links and divisible shipments only.
Loss rates must be estimates available at dispatch, not hindsight outcomes.
Optional dependencies: NumPy and SciPy. No external shipments are dispatched.
"""
import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix, eye, hstack, vstack


def _vector(value, name, *, positive=False):
    a = np.asarray(value, float)
    if a.ndim != 1 or len(a) == 0 or not np.isfinite(a).all() or (a < 0).any() or (positive and (a <= 0).any()):
        raise ValueError(f"{name} requires finite {'positive' if positive else 'nonnegative'} values")
    return a


def reallocate(supply, capacities, losses, conversion, *, required_receipt=0., reference=None):
    """Minimize raw loss subject to a product-equivalent receipt target.

    If the target is impossible, maximize received product first and report the
    shortfall. Then minimize raw loss at that maximum. Among loss-optimal flows,
    minimize L1 change from the provided dispatch proposal (if any), allowing
    1e-7 units of numerical slack in receipt and raw-loss objectives.
    If total raw supply exceeds transport capacity, return no invented feasible
    flow: all supplied material remains purchased but no complete dispatch exists.
    """
    s = _vector(supply, "supply")
    cap = _vector(capacities, "capacities")
    ell = _vector(losses, "losses")
    a = _vector(conversion, "conversion", positive=True)
    if len(s) != len(a) or len(cap) != len(ell) or (ell >= 1).any():
        raise ValueError("dimensions must match and loss fractions must be below one")
    if not np.isfinite(required_receipt) or required_receipt < 0:
        raise ValueError("required_receipt must be finite and nonnegative")
    if reference is not None:
        ref = np.asarray(reference, float)
        if ref.shape != (len(s), len(cap)) or not np.isfinite(ref).all() or (ref < 0).any():
            raise ValueError("reference requires a finite nonnegative supplier-by-carrier matrix")
    else:
        ref = None
    scope = "conditional pre-dispatch recourse with divisible shipments, unrestricted links and supplied loss estimates; no realized-loss or supplier-availability guarantee"
    deficit = max(0., float(s.sum()-cap.sum()))
    if deficit > 1e-7:
        return {"status": "TRANSPORT_CAPACITY_SHORTFALL", "all_supply_dispatched": False,
                "purchased_raw_quantity": float(s.sum()), "minimum_extra_raw_capacity": deficit,
                "shipments": None, "required_receipt": float(required_receipt), "scope": scope}
    active = np.flatnonzero(s > 0)
    if not len(active):
        return {"status": "TARGET_SHORTFALL" if required_receipt > 0 else "FEASIBLE",
                "all_supply_dispatched": True, "purchased_raw_quantity": 0.,
                "shipments": np.zeros((len(s),len(cap))).tolist(), "raw_loss": 0.,
                "received_product": 0., "maximum_product_receipt": 0.,
                "required_receipt": float(required_receipt), "receipt_shortfall": float(required_receipt),
                "changed_raw_quantity": float(ref.sum()/2) if ref is not None else None,
                "split_suppliers": 0, "certificates": [], "scope": scope}
    n,j = len(active),len(cap);m=n*j
    indices=np.arange(m)
    suppliers=coo_matrix((np.ones(m),(np.repeat(np.arange(n),j),indices)),shape=(n,m)).tocsr()
    carriers=coo_matrix((np.ones(m),(np.tile(np.arange(j),n),indices)),shape=(j,m)).tocsr()
    value=((1-ell)[None,:]/a[active,None]).ravel();loss=np.tile(ell,n)
    certificates=[]
    def solve(c, A, b, E, d):
        result=linprog(c,A_ub=A,b_ub=b,A_eq=E,b_eq=d,bounds=(0,None),method="highs")
        if not result.success:raise ValueError("recourse optimization failed: "+result.message)
        dual=float(b@result.ineqlin.marginals+d@result.eqlin.marginals)
        certificates.append({"objective":float(result.fun),"dual_objective":dual,"duality_gap":float(result.fun-dual)})
        return result
    best=solve(-value,carriers,cap,suppliers,s[active])
    maximum=float(-best.fun)
    target=min(float(required_receipt),maximum)
    objective_tolerance=1e-7
    rows=vstack([carriers,csr_matrix(-value[None,:])]).tocsr();upper=np.r_[cap,-target+objective_tolerance]
    cheapest=solve(loss,rows,upper,suppliers,s[active])
    flow=cheapest.x
    if ref is not None:
        # Auxiliary variables encode |flow-reference|. Exact equalities on two
        # floating-point optimum values can make a degenerate LP appear infeasible.
        # Keep a disclosed absolute tolerance rather than silently drop an objective.
        zero=csr_matrix((rows.shape[0],m));ident=eye(m,format="csr")
        A=vstack([hstack([rows,zero]),hstack([ident,-ident]),hstack([-ident,-ident]),
                  csr_matrix(np.r_[loss,np.zeros(m)][None,:])]).tocsr()
        b=np.r_[upper,ref[active].ravel(),-ref[active].ravel(),cheapest.fun+objective_tolerance]
        E=hstack([suppliers,csr_matrix((n,m))]).tocsr()
        d=s[active]
        stable=solve(np.r_[np.zeros(m),np.ones(m)],A,b,E,d)
        flow=stable.x[:m]
    full=np.zeros((len(s),j));full[active]=flow.reshape(n,j)
    received=float(value@flow);lost=float(loss@flow)
    residual=max(float(np.abs(full.sum(1)-s).max()), max(0.,float((full.sum(0)-cap).max())),max(0.,-float(full.min())))
    if residual>1e-6 or received<target-1e-6 or abs(lost-cheapest.fun)>1e-6:
        raise ValueError("recourse candidate violates conservation or lexicographic objectives")
    return {"status":"TARGET_SHORTFALL" if maximum<required_receipt-1e-6 else "FEASIBLE",
            "all_supply_dispatched":True,"purchased_raw_quantity":float(s.sum()),
            "shipments":full.tolist(),"raw_loss":lost,"received_product":received,
            "maximum_product_receipt":maximum,"required_receipt":float(required_receipt),
            "receipt_shortfall":max(0.,float(required_receipt-received)),
            "changed_raw_quantity":float(np.abs(full-ref).sum()/2) if ref is not None else None,
            "change_scope":"half L1 mass difference; only rerouted volume when proposal and supply have matching row sums",
            "split_suppliers":int(((full>1e-7).sum(1)>1).sum()),
            "objective_tolerance":objective_tolerance,
            "max_constraint_residual":residual,"certificates":certificates,"scope":scope}


def inventory_step(initial, received, requested_production, reserve_target):
    """Keep physical stock nonnegative and separate unmet output from reserves."""
    v=_vector([initial,received,requested_production,reserve_target],"inventory inputs")
    available=float(v[0]+v[1]);produced=min(available,float(v[2]));stock=available-produced
    return {"produced":produced,"unmet_production":float(v[2]-produced),
            "ending_inventory":stock,"reserve_shortfall":max(0.,float(v[3]-stock))}
