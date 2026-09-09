"""Optional numeric grouped-regression comparison with nested selection and honest baselines.

Requires NumPy and scikit-learn. Inputs are already audited numeric features;
this helper does not infer the independent unit, causal meaning, or prediction domain.
"""
import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import PolynomialFeatures, StandardScaler


def regression_metrics(actual, prediction, groups):
    actual, prediction, groups = np.asarray(actual), np.asarray(prediction), np.asarray(groups)
    error = (prediction-actual)**2
    total = np.sum((actual-actual.mean())**2)
    return {"row_rmse": float(np.sqrt(error.mean())),
            "group_rmse": float(np.sqrt(np.mean([error[groups==g].mean() for g in np.unique(groups)]))),
            "r2_descriptive": float(1-error.sum()/total) if total>0 else None}


def group_splits(groups, folds=5, seed=None):
    groups=np.asarray(groups)
    if groups.ndim!=1 or any(g is None or not str(g).strip() or (isinstance(g,(int,float,np.number)) and not np.isfinite(g)) for g in groups):
        raise ValueError("independent group IDs must be present and finite")
    if len(np.unique(groups))<folds or folds<2:
        raise ValueError("fold count must be between 2 and independent group count")
    if seed is not None:
        shuffled=np.random.default_rng(seed).permutation(np.unique(groups))
        result=[]
        for held_groups in np.array_split(shuffled,folds):
            test=np.flatnonzero(np.isin(groups,held_groups))
            train=np.flatnonzero(~np.isin(groups,held_groups))
            result.append((train,test))
        return result
    return [(train,test) for train,test in GroupKFold(folds).split(np.zeros((len(groups),1)),groups=groups)]


def validate_splits(groups, splits):
    groups=np.asarray(groups); seen=np.zeros(len(groups),dtype=int)
    if groups.ndim!=1 or any(g is None or not str(g).strip() or (isinstance(g,(int,float,np.number)) and not np.isfinite(g)) for g in groups):
        raise ValueError("independent group IDs must be present and finite")
    for train,test in splits:
        train,test=np.asarray(train),np.asarray(test)
        if train.ndim!=1 or test.ndim!=1 or not np.issubdtype(train.dtype,np.integer) or not np.issubdtype(test.dtype,np.integer):
            raise ValueError("split row indices must be one-dimensional integers")
        if len(train)==0 or len(test)==0 or np.intersect1d(train,test).size:
            raise ValueError("empty or overlapping train/test rows")
        if np.any(train<0) or np.any(test<0) or np.any(train>=len(groups)) or np.any(test>=len(groups)):
            raise ValueError("split row out of range")
        if set(groups[train]) & set(groups[test]):
            raise ValueError("the same independent group occurs in training and test")
        if len(np.unique(train))!=len(train) or len(np.unique(test))!=len(test):
            raise ValueError("duplicate row inside a split")
        seen[test]+=1
    if not np.all(seen==1):
        raise ValueError("each row must be predicted exactly once")


def make_model(spec):
    if spec["kind"]=="polynomial":
        return make_pipeline(PolynomialFeatures(spec["degree"],include_bias=False),StandardScaler(),
                             Ridge(alpha=spec["alpha"]) if "alpha" in spec else LinearRegression())
    if spec["kind"]=="forest":
        return RandomForestRegressor(n_estimators=spec["trees"],min_samples_leaf=spec["leaf"],
                                     max_features=spec.get("max_features",1.),random_state=spec["seed"],n_jobs=1)
    raise ValueError("unknown model kind")


def predict_fit(x,y,train,test,spec):
    if spec["kind"]=="mean":
        return np.full(len(test),float(np.mean(y[train]))),None
    columns=spec["columns"]
    model=make_model(spec)
    model.fit(x[np.ix_(train,columns)],y[train])
    return model.predict(x[np.ix_(test,columns)]),model


def select_candidate(x,y,groups,specs,folds,bounds):
    splits=group_splits(groups,folds)
    validate_splits(groups,splits)
    scores=[]
    for spec in specs:
        predicted=np.empty(len(y))
        for train,test in splits:
            raw,_=predict_fit(x,y,train,test,spec)
            predicted[test]=np.clip(raw,*bounds) if bounds is not None else raw
        scores.append(regression_metrics(y,predicted,groups)["group_rmse"])
    chosen=min(range(len(specs)),key=lambda i:(scores[i],i))
    return specs[chosen], [{"name":spec["name"],"inner_group_rmse":score} for spec,score in zip(specs,scores)]


def evaluate_grouped(x,y,groups,families,*,splits=None,outer_folds=5,inner_folds=4,bounds=None):
    x,y,groups=np.asarray(x,float),np.asarray(y,float),np.asarray(groups)
    if x.ndim!=2 or y.ndim!=1 or groups.ndim!=1 or not len(y) or len(x)!=len(y) or len(groups)!=len(y):
        raise ValueError("expected aligned numeric feature matrix, target and independent group IDs")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("missing/nonfinite values need an explicit preprocessing plan")
    if bounds is not None and (len(bounds)!=2 or not np.isfinite(bounds).all() or bounds[0]>=bounds[1] or np.any(y<bounds[0]) or np.any(y>bounds[1])):
        raise ValueError("invalid physical bounds or target outside them")
    if not families or any(not specs for specs in families.values()):
        raise ValueError("at least one explicitly specified candidate per family is required")
    for specs in families.values():
        for spec in specs:
            if spec["kind"]!="mean" and (not spec.get("columns") or any(type(c) is not int or not 0<=c<x.shape[1] for c in spec["columns"])):
                raise ValueError("invalid candidate feature columns")
    splits=group_splits(groups,outer_folds) if splits is None else splits
    validate_splits(groups,splits)
    splits=[(np.asarray(train),np.asarray(test)) for train,test in splits]
    result={"models":{},"folds":[{"fold":i,"train_rows":tr.tolist(),"test_rows":te.tolist(),
             "train_groups":np.unique(groups[tr]).tolist(),"test_groups":np.unique(groups[te]).tolist()}
             for i,(tr,te) in enumerate(splits)]}
    for name,specs in families.items():
        raw=np.empty(len(y)); choices=[]
        for fold,(train,test) in enumerate(splits):
            if len(specs)==1:
                selected=specs[0];scores=[]
            else:
                selected,scores=select_candidate(x[train],y[train],groups[train],specs,inner_folds,bounds)
            raw[test],_=predict_fit(x,y,train,test,selected)
            choices.append({"fold":fold,"selected":selected,"candidate_scores":scores})
        predicted=np.clip(raw,*bounds) if bounds is not None else raw.copy()
        result["models"][name]={"metrics":regression_metrics(y,predicted,groups),"raw_metrics":regression_metrics(y,raw,groups),
                                "prediction":predicted.tolist(),"raw_prediction":raw.tolist(),
                                "clipped_predictions":int(np.count_nonzero(raw!=predicted)),"selection":choices}
    result["scope"]="outer group-held-out predictions; hyperparameters chosen only in inner training-group folds; family comparisons remain exploratory unless a family-selection policy was nested"
    return result


def permute_group_descriptors(x,groups,columns,seed):
    """Exchange complete group-constant descriptors, never individual repeated rows."""
    x=np.asarray(x);groups=np.asarray(groups);unique=np.unique(groups)
    values=[]
    for group in unique:
        block=x[np.ix_(np.flatnonzero(groups==group),columns)]
        if not np.all(block==block[0]):
            raise ValueError("descriptor permutation requires group-constant columns")
        values.append(block[0])
    donor=np.random.default_rng(seed).permutation(len(unique))
    result=x.copy()
    for i,group in enumerate(unique):
        result[np.ix_(np.flatnonzero(groups==group),columns)]=values[donor[i]]
    return result,{str(group):str(unique[donor[i]]) for i,group in enumerate(unique)}
