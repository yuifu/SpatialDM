"""
Utils of permutation calculation
"""
import pandas as pd
import numpy as np
import random
from scipy import stats
import time
from tqdm import tqdm
from scipy.sparse import csc_matrix


# global variance
def var_compute(adata):
    N = adata.shape[0]
    nm = N ** 2 * (adata.obsp['weight'] * adata.obsp['weight'].T).sum() \
         - 2 * N * (adata.obsp['weight'].sum(1) * adata.obsp['weight'].sum(0)).sum() \
         + adata.obsp['weight'].sum() ** 2
    dm = N ** 2 * (N - 1) ** 2
    return nm / dm


# def perm_global(sample, k, PermTbl, LEN_div, ii,
#                 x, R, mean2, x_sq, y_sq):
#
#     idx_row = PermTbl.reshape(-1, 1)[:, 0]
#     value = adata.uns['exp.loc[idx_row, R] - mean2
#     value = value.mean(axis=1).values  # mean along row, e.g. ['Tgfbr1' 'Tgfbr2'], --> numpy
#     local_mat = np.matmul(adata.obsp['weight'], value.reshape(-1, adata.uns['N).T).T * x
#     adata.uns['global_perm[k, (LEN_div * ii):(LEN_div * (ii + 1))] = local_mat.sum(axis=1) / \
#                                     ((sum(x_sq) * sum(y_sq)) ** (1 / 2))
#     return



def generate_perm_tbl(adata, n_perm, num_spots):
    """shuffle neighbors for n_perm times by shuffling spot lables"""
    perm = np.zeros((n_perm, num_spots))
    perm = perm.astype(type(adata.obs_names.values[0]))
    mylist = list(adata.obs_names)
    for i in range(n_perm):
        random.shuffle(mylist)
        perm[i] = mylist
    return perm


def compute_var_local(sigma1_sq,sigma2_sq,wij_sq,n):
    var_I=2 * (n-1)**2/n**2 * sigma1_sq * sigma2_sq * wij_sq + \
        2 * (n-1)**2/n**2 * sigma1_sq * sigma2_sq
    std_I=var_I**(1/2)
    return std_I

def pair_selection(adata, n_perm, sel_ind, method):
    # local variables (only live in this function scope)
    ligand = adata.uns['ligand']
    receptor = adata.uns['receptor']
    for k in tqdm(sel_ind):
        start = time.time()
        L = ligand[k]
        R = receptor[k]
        mean1, mean2 = adata[:, L].X.mean().mean(), adata[:, R].X.mean().mean()
        x = (adata[:, L].X - mean1).mean(axis=1).values
        y = (adata[:, R].X - mean2).mean(axis=1).values
        x_sq, y_sq = x ** 2, y ** 2

        adata.uns['global_I'][k] = np.matmul(np.matmul(adata.obsp['weight'], y), x) / \
                      ((sum(x_sq) * sum(y_sq)) ** (1 / 2))
        if method in ['both', 'z-score']:
            adata.uns['z'][k] = adata.uns['global_I'][k] / adata.uns['st']
            adata.uns['z_p'][k] = stats.norm.sf(adata.uns['z'][k])
        if method in ['both', 'permutation']:
            PermTbl = generate_perm_tbl(adata, n_perm, adata.shape[0])
            idx_row = PermTbl.reshape(-1, 1)[:, 0]
            value = adata[idx_row, R].X - mean2
            value = value.mean(axis=1).values  # mean along row, e.g. ['Tgfbr1' 'Tgfbr2'], --> numpy
            local_mat = np.matmul(adata.obsp['weight'], value.reshape(n_perm, adata.shape[0]).T).T * x
            adata.uns['global_perm'][k] = local_mat.sum(axis=1) / \
                              ((sum(x_sq) * sum(y_sq)) ** (1 / 2))
        #print(str(k) + ' pairs global selection finished in: ' + str(time.time()-start))

def _standardise(X, Local=False, axis=None):
    """Standardise an array
    """
    X = X - X.mean(axis=axis, keepdims=True)
    if not Local:
        X = X / np.sqrt(np.sum(X**2, axis=axis, keepdims=True))
    return X

def pair_selection_matrix(adata, n_perm, sel_ind, method):
    # local variables (only live in this function scope)
    ligand = adata.uns['ligand'].loc[sel_ind]
    receptor = adata.uns['receptor'].loc[sel_ind]
    # ind = adata.uns['ind'][sel_ind]
    ## Check if the sparse matrix helps
    rbf_d = csc_matrix(adata.obsp['weight'])

    # averaged ligand values
    L1 = [pd.Series(x[0]).dropna().values for x in ligand.values]
    L_mat = [adata[:, L1[l]].X.astype(np.float)[:,0] for l in range(len(L1))]
    for i,k in enumerate(ligand.index):
        if len(ligand.loc[k].dropna()) > 1:
            L_mat[i] = adata[:, ligand.loc[k].dropna()].X.mean(1)

    # averaged receptor values
    R1 = [pd.Series(x[0]).dropna().values for x in receptor.values]
    R_mat = [adata[:, R1[r]].X.astype(np.float)[:,0] for r in range(len(R1))]
    for i,k in enumerate(receptor.index):
        if len(receptor.loc[k].dropna()) > 1:
            R_mat[i] = adata[:, receptor.loc[k].dropna()].X.mean(1)

    ## Check non-expressed pairs
    idx_use = (np.array(L_mat).sum(1) > 0) * (np.array(R_mat).sum(1) > 0)
    if (np.mean(idx_use) < 1):
        print('Warning: some LR pairs have no expression.')
    adata.uns['ligand'] = ligand.loc[idx_use]
    adata.uns['receptor'] = receptor.loc[idx_use]
    R_mat = np.array(R_mat).T
    L_mat = np.array(L_mat).T
    # adata.uns['ind'] = ind[idx_use]
    # adata.uns['ligand_use = ligand
    # adata.uns['receptor_use = receptor
    R_mat_use = _standardise(R_mat[:, idx_use], axis=0)
    L_mat_use = _standardise(L_mat[:, idx_use], axis=0)

    adata.uns['global_I'] = ((rbf_d @ L_mat_use) * R_mat_use).sum(axis=0)

    ## Calculate p values
    if method in ['both', 'z-score']:
        adata.uns['global_stat']['z']['z'] = adata.uns['global_I'] / adata.uns['global_stat']['z']['st']
        adata.uns['global_stat']['z']['z_p'] = stats.norm.sf(adata.uns['global_stat']['z']['z'])
    if method in ['both', 'permutation']:
        adata.uns['global_stat']['perm']['global_perm'] = np.zeros((L_mat_use.shape[1], n_perm))
        for i in tqdm(range(n_perm)):
            _idx = np.random.permutation(L_mat.shape[0])
            adata.uns['global_stat']['perm']['global_perm'][:, i] = np.sum(
                (rbf_d @ L_mat_use[_idx, :]) * R_mat_use, axis=0)


def spot_selection_matrix(adata, ligand, receptor, ind, n_perm, method):
    # local variables (only live in this function scope)
    # ligand = adata.uns['ligand'].loc[sel_ind]
    #     receptor = adata.uns['receptor'].loc[sel_ind]
    #     # ind = adata.uns['ind'][sel_ind]
    #     ## Check if the sparse matrix helps
    #     rbf_d = csc_matrix(adata.obsp['weight'])
    #
    #     # averaged ligand values
    #     L1 = [pd.Series(x[0]).dropna().values for x in ligand.values]
    #     L_mat = [adata[:, L1[l]].X.astype(np.float)[:,0] for l in range(len(L1))]
    #     for i,k in enumerate(ligand.index):
    #         if len(ligand.loc[k].dropna()) > 1:
    # averaged ligand values
    L1 = [pd.Series(x[0]).dropna().values for x in ligand.values]
    L_mat = [adata[:, L1[l]].X.astype(np.float)[:,0] for l in range(len(L1))]
    for i,k in enumerate(ligand.index):
        if len(ligand.loc[k].dropna()) > 1:
            L_mat[i] = adata[:, ligand.loc[k].dropna()].X.mean(1)

    # averaged receptor values
    R1 = [pd.Series(x[0]).dropna().values for x in receptor.values]
    R_mat = [adata[:, R1[r]].X.astype(np.float)[:, 0] for r in range(len(R1))]
    for i, k in enumerate(receptor.index):
        if len(receptor.loc[k].dropna()) > 1:
            R_mat[i] = adata[:, receptor.loc[k].dropna()].X.mean(1)
    R_mat = np.array(R_mat).T
    L_mat = np.array(L_mat).T
    pos = (L_mat > 0) + (R_mat > 0)
    R_mat_use = _standardise(R_mat, Local=True, axis=0)
    L_mat_use = _standardise(L_mat, Local=True, axis=0)
    wij_sq = (adata.obsp['weight'] ** 2).sum(1)
    rbf_d = csc_matrix(adata.obsp['weight'])

    adata.uns['local_stat']['local_I'] = (rbf_d @ R_mat_use) * L_mat_use
    adata.uns['local_stat']['local_I_R'] = (rbf_d @ L_mat_use) * R_mat_use
    N = adata.shape[0]
    ## Calculate p values
    if method in ['both', 'z-score']:
        norm_res1 = [stats.norm.fit(L_mat_use[:, i]) for i in range(L_mat_use.shape[1])]
        norm_res2 = [stats.norm.fit(R_mat_use[:, i]) for i in range(R_mat_use.shape[1])]
        norm_res1 = np.array(norm_res1)
        norm_res2 = np.array(norm_res2)
        mu1_ls, std_L_ls = norm_res1[:,0], norm_res1[:,1]
        mu2_ls, std_R_ls = norm_res2[:,0], norm_res2[:,1]
        sigma1_sq_ls = [(std1 * N / (N - 1)) for std1 in std_L_ls]
        sigma2_sq_ls = [(std2 * N / (N - 1)) for std2 in std_R_ls]
        std_ls = [compute_var_local(sigma1_sq, sigma2_sq, wij_sq, N) \
                    for (sigma1_sq, sigma2_sq) in zip(sigma1_sq_ls, sigma2_sq_ls)]
        adata.uns['local_z'] = (adata.uns['local_stat']['local_I'] + \
                                              adata.uns['local_stat']['local_I_R']).T / std_ls
        adata.uns['local_z_p'] = stats.norm.sf(adata.uns['local_z'])
        #adata.uns['local_z_p'] = np.where(pos.T == False, 1, adata.uns['local_z_p'])
        adata.uns['local_z_p'] = pd.DataFrame(adata.uns['local_z_p'], index=ind)

    if method in ['both', 'permutation']:
        adata.uns['local_stat']['local_permI'] = np.zeros((L_mat.shape[1], n_perm, N))
        adata.uns['local_stat']['local_permI_R'] = np.zeros((L_mat.shape[1], n_perm, N))
        for i in tqdm(range(n_perm)):
            _idx = np.random.permutation(L_mat.shape[0])
            adata.uns['local_stat']['local_permI'][:, i,:] = ((rbf_d @ R_mat_use[_idx, :]) * L_mat_use).T
            adata.uns['local_stat']['local_permI_R'][:, i,:] = ((rbf_d @ L_mat_use[_idx, :]) * R_mat_use).T
        adata.uns['local_perm_p'] = (np.expand_dims(adata.uns['local_stat']['local_I'].T + \
                                                 adata.uns['local_stat']['local_I_R'].T, 1) <= \
         (adata.uns['local_stat']['local_permI'] + adata.uns['local_stat']['local_permI_R'])).sum(1) / n_perm
        #adata.uns['local_perm_p'] = np.where(pos.T == False, 1, adata.uns['local_perm_p'])
        adata.uns['local_perm_p'] = pd.DataFrame(adata.uns['local_perm_p'], index=ind)

def compute_pathway(sample=None,
                    all_interactions=None,
        interaction_ls=None, name=None, dic=None):
    """
    Compute enriched pathways for a list of pairs or a dic of SpatialDE results.
    :param sample: spatialdm obj
    :param ls: a list of LR interaction names for the enrichment analysis
    :param path_name: str. For later recall sample.path_summary[path_name]
    :param dic: a dic of SpatialDE results (See tutorial)
    """
    if interaction_ls is not None:
        dic = {name: interaction_ls}
    if sample is not None:
        all_interactions = sample.uns['geneInter']
    df = pd.DataFrame(all_interactions.groupby('pathway_name').interaction_name)
    df = df.set_index(0)
    total_feature_num = len(all_interactions)
    result = []
    for n,ls in dic.items():
        qset = set([x.upper() for x in ls]).intersection(all_interactions.index)
        query_set_size = len(qset)
        for modulename, members in df.iterrows():
            module_size = len(members.values[0])
            overlap_features = qset.intersection(members.values[0])
            overlap_size = len(overlap_features)

            negneg = total_feature_num + overlap_size - module_size - query_set_size
            # Fisher's exact test
            p_FET = stats.fisher_exact([[overlap_size, query_set_size - overlap_size],
                                        [module_size - overlap_size, negneg]], 'greater')[1]
            result.append((p_FET, modulename, module_size, overlap_size, overlap_features, n))
    result = pd.DataFrame(result).set_index(1)
    result.columns = ['fisher_p', 'pathway_size', 'selected', 'selected_inters', 'name']
    if sample is not None:
        sample.uns['pathway_summary'] = result
    return result

# def permutation(sample, LEN_div, ii,
#                 x, y, L, R, mean1, mean2):
#     PermTbl_sub = adata.uns['PermTbl'][(LEN_div * ii):(LEN_div * (ii + 1)), :]
#     idx_row = PermTbl_sub.reshape(-1, 1)[:, 0]
#     value = adata.uns['adata[idx_row, R] - mean2
#     value = value.mean(axis=1).values  # mean along row, e.g. ['Tgfbr1' 'Tgfbr2'], --> numpy
#     value_R = adata.uns['adata[idx_row, L] - mean1
#     value_R = value_R.mean(axis=1).values
#     adata.uns['local_permI[:, (LEN_div * ii):(LEN_div * (ii + 1)), :] = \
#         np.matmul(adata.obsp['weight'], value.reshape(-1, N).T).T * x
#     adata.uns['local_permI_R[:, (LEN_div * ii):(LEN_div * (ii + 1)), :] = \
#         np.matmul(adata.obsp['weight'], value_R.reshape(-1, N).T).T * y
#     return
