"""Joint temperature and pol-only Wiener and inverse variance filtering module.

"""

import numpy  as np
import healpy as hp
from plancklens.qcinv import util, template_removal
#import template_removal
from plancklens.utils import clhash

from .util_alm import teblm
from . import dense


def calc_prep(maps, s_cls, n_inv_filt):
    tmap, qmap, umap = np.copy(maps[0]), np.copy(maps[1]), np.copy(maps[2])
    assert (len(tmap) == len(qmap));
    assert (len(tmap) == len(umap))
    npix = len(tmap)

    n_inv_filt.apply_map([tmap, qmap, umap])
    lmax = len(n_inv_filt.b_transf) - 1

    tlm, elm, blm = hp.map2alm([tmap, qmap, umap], lmax=lmax, iter=0, pol=True)
    tlm *= npix / (4. * np.pi)
    elm *= npix / (4. * np.pi)
    blm *= npix / (4. * np.pi)

    hp.almxfl(tlm, n_inv_filt.b_transf, inplace=True)
    hp.almxfl(elm, n_inv_filt.b_transf, inplace=True)
    hp.almxfl(blm, n_inv_filt.b_transf, inplace=True)
    return teblm([tlm, elm, blm])


def apply_fini(alm, s_cls, n_inv_filt):
    sfilt = alm_filter_sinv(s_cls)
    ret = sfilt.calc(alm)
    alm.tlm[:] = ret.tlm[:]
    alm.elm[:] = ret.elm[:]
    alm.blm[:] = ret.blm[:]


def apply_finiMLIK(alm, s_cls, n_inv_filt):
    pass

# ===
class dot_op:
    def __init__(self):
        pass

    def __call__(self, alm1, alm2):
        assert alm1.lmaxt == alm2.lmaxt, (alm1.lmaxt, alm2.lmaxt)
        assert alm1.lmaxe == alm2.lmaxe, (alm1.lmaxe, alm2.lmaxe)
        assert alm1.lmaxb == alm2.lmaxb, (alm1.lmaxb, alm2.lmaxb)

        ret =  np.sum(hp.alm2cl(alm1.tlm, alm2.tlm) * (2. * np.arange(0, alm1.lmaxt + 1) + 1))
        ret += np.sum(hp.alm2cl(alm1.elm, alm2.elm) * (2. * np.arange(0, alm1.lmaxe + 1) + 1))
        ret += np.sum(hp.alm2cl(alm1.blm, alm2.blm) * (2. * np.arange(0, alm1.lmaxb + 1) + 1))
        return ret


class fwd_op:
    def __init__(self, s_cls, n_inv_filt):
        self.s_inv_filt = alm_filter_sinv(s_cls)
        self.n_inv_filt = n_inv_filt

    def hashdict(self):
        return {'s_inv_filt': self.s_inv_filt.hashdict(),
                'n_inv_filt': self.n_inv_filt.hashdict()}

    def __call__(self, alm):
        return self.calc(alm)

    def calc(self, alm):
        nlm = alm * 1.0
        self.n_inv_filt.apply_alm(nlm)

        slm = self.s_inv_filt.calc(alm)

        return nlm + slm


# ===

class pre_op_diag:
    def __init__(self, s_cls, n_inv_filt):
        s_inv_filt = alm_filter_sinv(s_cls)
        assert ((s_inv_filt.lmax + 1) >= len(n_inv_filt.b_transf))

        ninv_ftl, ninv_fel, ninv_fbl = n_inv_filt.get_ftebl()

        lmax = len(n_inv_filt.b_transf) - 1

        flmat = s_inv_filt.slinv[0:lmax + 1, :, :]

        flmat[:, 0, 0] += ninv_ftl
        flmat[:, 1, 1] += ninv_fel
        flmat[:, 2, 2] += ninv_fbl
        flmat = np.linalg.pinv(flmat)
        self.flmat = flmat

    def __call__(self, talm):
        return self.calc(talm)

    def calc(self, alm):
        tmat = self.flmat

        rtlm = hp.almxfl(alm.tlm, tmat[:, 0, 0]) + hp.almxfl(alm.elm, tmat[:, 0, 1]) + hp.almxfl(alm.blm, tmat[:, 0, 2])
        relm = hp.almxfl(alm.tlm, tmat[:, 1, 0]) + hp.almxfl(alm.elm, tmat[:, 1, 1]) + hp.almxfl(alm.blm, tmat[:, 1, 2])
        rblm = hp.almxfl(alm.tlm, tmat[:, 2, 0]) + hp.almxfl(alm.elm, tmat[:, 2, 1]) + hp.almxfl(alm.blm, tmat[:, 2, 2])
        return teblm([rtlm, relm, rblm])

def pre_op_dense(lmax, fwd_op, cache_fname=None):
    """Missing doc. """
    return dense.pre_op_dense_tp(lmax, fwd_op, cache_fname=cache_fname)

# ===

class alm_filter_sinv:
    def __init__(self, s_cls, lmax):
        slmat = np.zeros((lmax + 1, 3, 3))  # matrix of TEB correlations at each l.
        slmat[:, 0, 0] = getattr(s_cls, 'cltt', np.zeros(lmax + 1))[:lmax+1]
        slmat[:, 0, 1] = getattr(s_cls, 'clte', np.zeros(lmax + 1))[:lmax+1]
        slmat[:, 1, 0] = slmat[:, 0, 1]
        slmat[:, 0, 2] = getattr(s_cls, 'cltb', np.zeros(lmax + 1))[:lmax+1]
        slmat[:, 2, 0] = slmat[:, 0, 2]
        slmat[:, 1, 1] = getattr(s_cls, 'clee', np.zeros(lmax + 1))[:lmax+1]
        slmat[:, 1, 2] = getattr(s_cls, 'cleb', np.zeros(lmax + 1))[:lmax+1]
        slmat[:, 2, 1] = slmat[:, 1, 2]
        slmat[:, 2, 2] = getattr(s_cls, 'clbb', np.zeros(lmax + 1))[:lmax+1]

        slinv = np.linalg.pinv(slmat)

        self.lmax = lmax
        self.slinv = slinv

    def calc(self, alm):
        tmat = self.slinv

        rtlm = hp.almxfl(alm.tlm, tmat[:, 0, 0]) + hp.almxfl(alm.elm, tmat[:, 0, 1]) + hp.almxfl(alm.blm, tmat[:, 0, 2])
        relm = hp.almxfl(alm.tlm, tmat[:, 1, 0]) + hp.almxfl(alm.elm, tmat[:, 1, 1]) + hp.almxfl(alm.blm, tmat[:, 1, 2])
        rblm = hp.almxfl(alm.tlm, tmat[:, 2, 0]) + hp.almxfl(alm.elm, tmat[:, 2, 1]) + hp.almxfl(alm.blm, tmat[:, 2, 2])
        return teblm([rtlm, relm, rblm])

    def hashdict(self):
        return {'slinv': clhash(self.slinv.flatten())}


class alm_filter_ninv:
    def __init__(self, n_inv, b_transf, marge_monopole=False, marge_dipole=False, marge_maps_t=[], marge_maps_p=[]):
        # n_inv = [util.load_map(n[:]) for n in n_inv]
        self.n_inv = []
        for i, tn in enumerate(n_inv):
            if isinstance(tn, list):
                n_inv_prod = util.load_map(tn[0][:])
                if len(tn) > 1:
                    for n in tn[1:]:
                        n_inv_prod = n_inv_prod * util.load_map(n[:])
                self.n_inv.append(n_inv_prod)
                # assert (np.std(self.n_inv[i][np.where(self.n_inv[i][:] != 0.0)]) / np.average(
                #    self.n_inv[i][np.where(self.n_inv[i][:] != 0.0)]) < 1.e-7)
            else:
                self.n_inv.append(util.load_map(n_inv[i]))

        n_inv = self.n_inv
        npix = len(n_inv[0])
        nside = hp.npix2nside(npix)
        for n in n_inv[1:]:
            assert (len(n) == npix)

        templates_t = []
        templates_t_hash = []
        for tmap in [util.load_map(m) for m in marge_maps_t]:
            assert (npix == len(tmap))
            templates_t.append(template_removal.template_map(tmap))
            templates_t_hash.append(clhash(tmap))

        if marge_monopole: templates_t.append(template_removal.template_monopole())
        if marge_dipole: templates_t.append(template_removal.template_dipole())

        if len(templates_t) != 0:
            nmodes = np.sum([t.nmodes for t in templates_t])
            modes_idx_t = np.concatenate(([t.nmodes * [int(im)] for im, t in enumerate(templates_t)]))
            modes_idx_i = np.concatenate(([range(0, t.nmodes) for t in templates_t]))

            Pt_Nn1_P = np.zeros((nmodes, nmodes))
            for ir in range(0, nmodes):
                tmap = np.copy(n_inv[0])
                templates_t[modes_idx_t[ir]].apply_mode(tmap, int(modes_idx_i[ir]))

                ic = 0
                for tc in templates_t[0:modes_idx_t[ir] + 1]:
                    Pt_Nn1_P[ir, ic:(ic + tc.nmodes)] = tc.dot(tmap)
                    Pt_Nn1_P[ic:(ic + tc.nmodes), ir] = Pt_Nn1_P[ir, ic:(ic + tc.nmodes)]
                    ic += tc.nmodes

            self.Pt_Nn1_P_inv = np.linalg.inv(Pt_Nn1_P)

        self.n_inv = n_inv
        self.b_transf = b_transf[:]

        self.marge_monopole = marge_monopole
        self.marge_dipole = marge_dipole

        self.templates_t = templates_t
        self.templates_t_hash = templates_t_hash

        assert len(marge_maps_p) == 0
        self.templates_p = []

        self.npix = npix
        self.nside = nside

    def get_ftebl(self):
        if len(self.n_inv) == 2:  # TT, 1/2(QQ+UU)
            n_inv_cl_t = np.sum(self.n_inv[0]) / (4.0 * np.pi) * self.b_transf ** 2
            n_inv_cl_p = np.sum(self.n_inv[1]) / (4.0 * np.pi) * self.b_transf ** 2

            return n_inv_cl_t, n_inv_cl_p, n_inv_cl_p
        elif len(self.n_inv) == 4:  # TT, QQ, QU, UU
            n_inv_cl_t = np.sum(self.n_inv[0]) / (4.0 * np.pi) * self.b_transf ** 2
            n_inv_cl_p = np.sum(0.5 * (self.n_inv[1] + self.n_inv[3])) / (4.0 * np.pi) * self.b_transf ** 2

            return n_inv_cl_t, n_inv_cl_p, n_inv_cl_p
        else:
            assert 0

    def hashdict(self):
        return {'n_inv': [clhash(n) for n in self.n_inv],
                'b_transf': clhash(self.b_transf),
                'marge_monopole': self.marge_monopole,
                'marge_dipole': self.marge_dipole,
                'templates_t_hash': self.templates_t_hash}

    def degrade(self, nside):
        if nside == self.nside:
            return self
        else:
            print("DEGRADING WITH NO MARGE MAPS")
            marge_maps_t = []
            marge_maps_p = []
        return alm_filter_ninv([hp.ud_grade(n, nside, power=-2) for n in self.n_inv], self.b_transf,
                                   self.marge_monopole, self.marge_dipole, marge_maps_t, marge_maps_p)

    def apply_alm(self, alm):
        # applies Y^T N^{-1} Y
        lmax = alm.lmax

        hp.almxfl(alm.tlm, self.b_transf, inplace=True)
        hp.almxfl(alm.elm, self.b_transf, inplace=True)
        hp.almxfl(alm.blm, self.b_transf, inplace=True)

        tmap, qmap, umap = hp.alm2map((alm.tlm, alm.elm, alm.blm), self.nside, verbose=False, pol=True)
        # qmap, umap = hp.alm2map_spin((alm.elm, alm.blm), self.nside, 2)

        self.apply_map([tmap, qmap, umap])

        ttlm, telm, tblm = hp.map2alm([tmap, qmap, umap], iter=0, pol=True, lmax=lmax)
        alm.tlm[:] = ttlm
        alm.elm[:] = telm
        alm.blm[:] = tblm

        alm.tlm[:] *= (self.npix / (4. * np.pi))
        alm.elm[:] *= (self.npix / (4. * np.pi))
        alm.blm[:] *= (self.npix / (4. * np.pi))

        hp.almxfl(alm.tlm, self.b_transf, inplace=True)
        hp.almxfl(alm.elm, self.b_transf, inplace=True)
        hp.almxfl(alm.blm, self.b_transf, inplace=True)

    def apply_map(self, amap):
        [tmap, qmap, umap] = amap

        # applies N^{-1}
        if len(self.n_inv) == 2:  # TT, QQ=UU
            tmap *= self.n_inv[0]
            qmap *= self.n_inv[1]
            umap *= self.n_inv[1]
        elif len(self.n_inv) == 4:  # TT, QQ, QU, UU
            qmap_copy = qmap.copy()

            tmap *= self.n_inv[0]
            qmap *= self.n_inv[1]
            qmap += self.n_inv[2] * umap

            umap *= self.n_inv[3]
            umap += self.n_inv[2] * qmap_copy

            del qmap_copy
        else:
            assert 0

        if len(self.templates_t) != 0:
            coeffs = np.concatenate(([t.dot(tmap) for t in self.templates_t]))
            coeffs = np.dot(self.Pt_Nn1_P_inv, coeffs)

            pmodes = np.zeros(len(self.n_inv[0]))
            im = 0
            for t in self.templates_t:
                t.accum(pmodes, coeffs[im:(im + t.nmodes)])
                im += t.nmodes
            pmodes *= self.n_inv[0]
            tmap -= pmodes
