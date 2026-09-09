"""Mixed-integer supplier choice and lexicographic material/transport planning."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linprog, milp
from scipy.sparse import coo_matrix, csr_matrix, hstack, vstack
from prepare import write


def network(facts, scale=1., cap_override=None, losses=None):
    cap=np.asarray(facts["supply_cap"] if cap_override is None else cap_override)*scale
    a=np.array(facts["conversion"]);price=np.array(facts["price"])
    loss=np.array(facts["carrier_mean_loss"] if losses is None else losses)
    n=len(cap);m=8*n
    rows=np.r_[np.repeat(np.arange(n),8), n+np.tile(np.arange(8),n)]
    cols=np.r_[np.arange(m),np.arange(m)]
    A=coo_matrix((np.ones(2*m),(rows,cols)),shape=(n+8,m)).tocsr()
    b=np.r_[cap,np.full(8,6000.)]
    yield_=((1-loss)[None,:]/a[:,None]).ravel()
    cost=np.repeat(price,8);rawloss=np.tile(loss,n)
    return cap,a,price,loss,A,b,yield_,cost,rawloss


def lp_solve(c,A,b,Aeq=None,beq=None):
    r=linprog(c,A_ub=A,b_ub=b,A_eq=Aeq,b_eq=beq,bounds=(0,None),method="highs")
    if not r.success:raise ValueError(r.message)
    # Independently checkable primal and dual objective values for this LP.
    dual=float(np.dot(b,r.ineqlin.marginals))
    if beq is not None:dual+=float(np.dot(beq,r.eqlin.marginals))
    return r,{"objective":float(r.fun),"dual_objective":dual,"gap":float(r.fun-dual),"status":r.message}


def count_suppliers(facts, target, allowed=None):
    cap,a,price,loss,A,b,yield_,cost,rawloss=network(facts)
    n=len(cap);m=8*n
    if allowed is not None:
        mask=np.zeros(n);mask[allowed]=1;cap=cap*mask
    # Supply bounds bind binary contract activation; carrier bounds remain raw m3.
    choice=coo_matrix((-cap,(np.arange(n),np.arange(n))),shape=(n+8,n)).tocsr()
    rows=hstack([A,choice]).tocsr();rhs=np.r_[np.zeros(n),np.full(8,6000.)]
    rows=vstack([rows,csr_matrix(np.r_[-yield_,np.zeros(n)][None,:])]).tocsr();rhs=np.r_[rhs,-target]
    c=np.r_[np.zeros(m),np.ones(n)]
    bounds=Bounds(np.zeros(m+n),np.r_[np.full(m,np.inf),np.ones(n)])
    integer=np.r_[np.zeros(m),np.ones(n)]
    r=milp(c,integrality=integer,bounds=bounds,constraints=LinearConstraint(rows,-np.inf,rhs),options={"time_limit":90.,"mip_rel_gap":0.})
    if r.x is None:raise ValueError(r.message)
    number=int(np.rint(r.x[m:]).sum())
    optimistic=np.sort(cap/np.array(facts["conversion"])*(1-min(loss)))[::-1]
    optimistic_count=int(np.searchsorted(np.cumsum(optimistic),target)+1)
    if not r.success and optimistic_count!=number:raise ValueError("minimum supplier count not certified before time cap")
    # Economic optimum among all sets of that minimum size.
    rows2=vstack([rows,csr_matrix(np.r_[np.zeros(m),np.ones(n)][None,:])]).tocsr();rhs2=np.r_[rhs,number]
    economic=milp(np.r_[cost,np.zeros(n)],integrality=integer,bounds=bounds,
                  constraints=LinearConstraint(rows2,-np.inf,rhs2),options={"time_limit":90.,"mip_rel_gap":1e-7})
    if economic.x is None:raise ValueError(economic.message)
    x=economic.x[:m].reshape(n,8)
    certificate={"minimum_supplier_count":number,"optimistic_sorted_capacity_lower_bound":optimistic_count,
                 "count_solver_status":r.message,"count_mip_dual_bound":float(r.mip_dual_bound),
                 "economic_status":economic.message,"economic_mip_gap":float(economic.mip_gap),
                 "economic_lower_bound":float(economic.mip_dual_bound),"economic_objective":float(economic.fun)}
    return x,certificate


def material_plan(facts,target,mode="cost",cap_override=None):
    cap,a,price,loss,A,b,yield_,cost,rawloss=network(facts,cap_override=cap_override)
    eq=csr_matrix(yield_[None,:]);beq=np.array([target]);proof=[]
    objectives=[]
    if mode=="A_then_C":
        isA=np.repeat(np.array(facts["kinds"])=="A",8)
        isC=np.repeat(np.array(facts["kinds"])=="C",8)
        objectives=[-yield_*isA,isC.astype(float)]
    objectives.append(cost)
    for objective in objectives:
        r,cert=lp_solve(objective,A,b,eq,beq);proof.append(cert)
        # Exact equality retains the earlier lexicographic optimum.
        eq=vstack([eq,csr_matrix(objective[None,:])]).tocsr();beq=np.r_[beq,r.fun]
    r,cert=lp_solve(rawloss,A,b,eq,beq);proof.append(cert)
    return r.x.reshape(len(cap),8),proof


def transfer_fixed_supply(facts,x,target):
    cap,a,price,loss,A,b,yield_,cost,rawloss=network(facts)
    n=len(cap);supply=x.sum(1)
    eq=A[:n];rhs=supply
    rows=vstack([A[n:],csr_matrix(-yield_[None,:])]).tocsr();ub=np.r_[b[n:],-target]
    r,proof=lp_solve(rawloss,rows,ub,eq,rhs)
    return r.x.reshape(n,8),proof


def capacity(facts,scale=1.,losses=None,cap_override=None):
    cap,a,price,loss,A,b,yield_,cost,rawloss=network(facts,scale,cap_override,losses)
    r,proof=lp_solve(-yield_,A,b)
    return -r.fun,r.x.reshape(len(cap),8),proof


def record_plan(facts,shipments,production):
    y=np.asarray(shipments);a=np.array(facts["conversion"]);r=np.array(facts["supply_rate"])
    loss=np.array(facts["carrier_mean_loss"]);price=np.array(facts["price"])
    expected_supply=y.sum(2)
    orders=np.divide(expected_supply,r[None,:],out=np.zeros_like(expected_supply),where=r[None,:]>0)
    arrivals=(y*(1-loss)[None,None,:]/a[None,:,None]).sum((1,2))
    inventory=facts["initial_inventory_product_equivalent"]+np.cumsum(arrivals-production)
    raw_by_type={k:float(expected_supply[:,np.array(facts["kinds"])==k].sum()) for k in "ABC"}
    nlinks=(y>1e-7).sum(2)
    return {"production_per_week":float(production),"orders":orders.tolist(),"shipments":y.tolist(),
            "arrivals_product_equivalent":arrivals.tolist(),"ending_inventory_product_equivalent":inventory.tolist(),
            "purchase_cost_index":float((expected_supply*price).sum()),"raw_material_volume":float(expected_supply.sum()),
            "raw_by_type":raw_by_type,"expected_transport_loss":float((y*loss[None,None,:]).sum()),
            "active_suppliers":int((expected_supply.sum(0)>1e-6).sum()),
            "split_supplier_weeks":int((nlinks>1).sum()),"max_carrier_load":float(y.sum(1).max()),
            "stock_target":float(2*production),"min_stock_slack":float(inventory.min()-2*production),
            "scope":"forecast conditional on source-derived mean response and standard contract caps; no future observed performance claim"}


def solve(run):
    f=json.loads((run/"artifacts/facts.json").read_text());d=f["demand"]
    y2,count=count_suppliers(f,d)
    y2,transport2=transfer_fixed_supply(f,y2,d)
    q2=record_plan(f,np.repeat(y2[None,:,:],24,axis=0),d)
    q2["certificates"]={"supplier_selection":count,"transport":transport2}
    print("Q2",count,flush=True)
    y3,proof3=material_plan(f,d,"A_then_C")
    q3=record_plan(f,np.repeat(y3[None,:,:],24,axis=0),d);q3["certificates"]=proof3
    steady,ymax,proofmax=capacity(f)
    immediate=min(steady,(steady+f["initial_inventory_product_equivalent"])/3)
    first,firstproof=material_plan(f,3*immediate-f["initial_inventory_product_equivalent"])
    later,laterproof=material_plan(f,immediate)
    q4=record_plan(f,np.concatenate([first[None,:,:],np.repeat(later[None,:,:],23,axis=0)]),immediate)
    q4["certificates"]={"steady":proofmax,"first_week":firstproof,"later_weeks":laterproof}
    q4["steady_capacity"]=steady;q4["steady_increase_percent"]=100*(steady/d-1)
    q4["immediate_increase_percent"]=100*(immediate/d-1)
    # Alternative cap assumptions are sensitivity scenarios, not ground truth.
    sensitivity=[]
    for scale in (.8,.9,1.,1.1,1.2):
        p,_,proof=capacity(f,scale)
        sensitivity.append({"contract_capacity_scale":scale,"steady_capacity":p,"immediate_capacity":min(p,(p+2*d)/3),"lp_proof":proof})
    q90=np.array(f["order_cap_q90"])*np.array(f["supply_rate"])
    p,_,proof=capacity(f,cap_override=q90)
    sensitivity.append({"contract_envelope":"positive_order_90th_percentile","steady_capacity":p,"scope":"more aggressive order extrapolation, not certified sustainable capacity","lp_proof":proof})
    p,_,proof=capacity(f,losses=f["carrier_p95_loss"])
    sensitivity.append({"loss_scenario":"carrier marginal 95th percentiles jointly","steady_capacity":p,"lp_proof":proof})
    write(run/"artifacts/plans.json",{"Q2":q2,"Q3":q3,"Q4":q4})
    write(run/"artifacts/capacity-sensitivity.json",sensitivity)
    print({q:{k:v for k,v in r.items() if k not in ("orders","shipments","certificates","arrivals_product_equivalent","ending_inventory_product_equivalent")} for q,r in (("Q2",q2),("Q3",q3),("Q4",q4))},flush=True)


if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("run",type=Path);solve(ap.parse_args().run)
