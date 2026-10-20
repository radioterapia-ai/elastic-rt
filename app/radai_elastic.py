# -*- coding: utf-8 -*-
import math


SEM_APROVACAO = (
    u"A fusão é uma sugestão não aprovada. Conferir o alinhamento na região "
    u"que importa para a decisão é ato médico, e nenhum número aqui "
    u"substitui essa conferência."
)

NAO_PROPAGA = (
    u"Este módulo NÃO propaga contorno. Ele mostra e mede a deformação; ele "
    u"não move estrutura de uma série para a outra. Levar um contorno por um "
    u"campo cuja qualidade ninguém olhou é exatamente o que o TG-132 existe "
    u"para evitar — e uma estrutura propagada chega ao plano com aparência de "
    u"contorno conferido."
)

REFERENCIA_E_NOSSA = (
    u"A referência é este módulo, e não outro programa: o campo deformável "
    u"de outros sistemas raramente é exportado em formato aberto, então isto "
    u"não é segunda opinião contra eles. O que se mede é a transformação "
    u"contra ela mesma."
)

LIMIAR_E_NOSSO = (
    u"Os limiares abaixo são deste aplicativo. O TG-132 exige QA por caso e "
    u"recomenda que cada serviço estabeleça a própria tolerância — ele não "
    u"publica um limiar universal, e atribuir um a ele seria inventar fonte."
)

JAC_DOBRA = 0.0
JAC_MAGRO = 0.20
JAC_GORDO = 5.00
CONSIST_P95_MM = 2.0
DESLOC_MAX_MM = 50.0
COBERTURA_MIN_PARTE = 50.0
MALHA_MENOS_LIVRE = 6

VEREDITOS = ("passa", "atencao", "reprova")

LIMIAR_AR_HU = -500.0
LIMIAR_CORPO_HU = -300.0
FRACAO_CORPO_SINAL = 0.10


def _sitk():
    import SimpleITK as sitk
    return sitk


def _minimo(img):
    try:
        sitk = _sitk()
        if isinstance(img, sitk.Image):
            f = sitk.MinimumMaximumImageFilter()
            f.Execute(img)
            return float(f.GetMinimum())
    except ImportError:
        pass
    import numpy as np
    return float(np.min(img))


def eh_hu(img):
    return _minimo(img) < LIMIAR_AR_HU


def fundo_de(img):
    return -1024.0 if eh_hu(img) else _minimo(img)


def preparar(img, esp_mm=2.0):
    sitk = _sitk()
    ent_esp = img.GetSpacing()
    ent_tam = img.GetSize()
    saida = [int(round(ent_tam[i] * ent_esp[i] / esp_mm)) for i in range(3)]
    r = sitk.ResampleImageFilter()
    r.SetOutputSpacing((esp_mm, esp_mm, esp_mm))
    r.SetSize([max(4, s) for s in saida])
    r.SetOutputOrigin(img.GetOrigin())
    r.SetOutputDirection(img.GetDirection())
    r.SetInterpolator(sitk.sitkLinear)
    r.SetDefaultPixelValue(fundo_de(img))
    return sitk.Cast(r.Execute(img), sitk.sitkFloat32)


def _centro(img):
    tam = img.GetSize()
    return img.TransformContinuousIndexToPhysicalPoint(
        [(t - 1) / 2.0 for t in tam])


INICIOS = ("coordenadas", "centros")


def inicio_do_rigido(fixa, movel):
    sitk = _sitk()
    ident = sitk.Euler3DTransform()
    ident.SetCenter(_centro(fixa))
    geo = sitk.CenteredTransformInitializer(
        fixa, movel, sitk.Euler3DTransform(),
        sitk.CenteredTransformInitializerFilter.GEOMETRY)
    m = sitk.ImageRegistrationMethod()
    m.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    m.SetMetricSamplingStrategy(m.RANDOM)
    m.SetMetricSamplingPercentage(0.10, seed=20260825)
    m.SetInterpolator(sitk.sitkLinear)
    valores = {}
    partidas = (("coordenadas", ident), ("centros", geo))
    for nome, tx in partidas:
        try:
            m.SetInitialTransform(tx, inPlace=False)
            v = float(m.MetricEvaluate(fixa, movel))
            valores[nome] = v if math.isfinite(v) else None
        except RuntimeError:
            valores[nome] = None
    validos = [(valores[n], i, n, tx) for i, (n, tx) in enumerate(partidas)
               if valores[n] is not None]
    if not validos:
        return geo, "centros", valores
    validos.sort(key=lambda x: (x[0], x[1]))
    _v, _i, nome, tx = validos[0]
    return tx, nome, valores


def registrar_rigido(fixa, movel, passos=100, prog=None, inicial=None):
    sitk = _sitk()
    ini = inicial
    if ini is None:
        ini = sitk.CenteredTransformInitializer(
            fixa, movel, sitk.Euler3DTransform(),
            sitk.CenteredTransformInitializerFilter.GEOMETRY)
    m = sitk.ImageRegistrationMethod()
    m.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    m.SetMetricSamplingStrategy(m.RANDOM)
    m.SetMetricSamplingPercentage(0.10, seed=20260825)
    m.SetInterpolator(sitk.sitkLinear)
    m.SetOptimizerAsRegularStepGradientDescent(
        learningRate=2.0, minStep=1e-4, numberOfIterations=passos,
        gradientMagnitudeTolerance=1e-8)
    m.SetOptimizerScalesFromPhysicalShift()
    m.SetShrinkFactorsPerLevel([4, 2, 1])
    m.SetSmoothingSigmasPerLevel([2.0, 1.0, 0.0])
    m.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    m.SetInitialTransform(ini, inPlace=False)
    if prog is not None:
        m.AddCommand(sitk.sitkIterationEvent,
                     lambda: prog(u"rígido", m.GetOptimizerIteration(),
                                  m.GetMetricValue()))
    return m.Execute(fixa, movel)


def mascara_da_metrica(fixa, movel, rigida):
    import numpy as np
    try:
        corpo = mascara_corpo(fixa)
        sup = suporte(movel, compor(rigida, None), fixa)
    except Exception:
        return None
    if corpo is None or sup is None or corpo.shape != sup.shape:
        return None
    m = np.asarray(corpo, dtype=bool) & np.asarray(sup, dtype=bool)
    if int(m.sum()) < MASCARA_MIN_VOXELS:
        return None
    return m


MASCARA_MIN_VOXELS = 50000


def registrar_deformavel(fixa, movel, inicial, malha=8, passos=50,
                         amostra=0.01, avaliacoes=300, prog=None,
                         mascara=None):
    sitk = _sitk()
    dom = [max(2, int(round(malha * fixa.GetSize()[i] / max(fixa.GetSize()))))
           for i in range(3)]
    # GUARDA: B-spline, e nao Demons difeomorfico: o B-spline PODE dobrar, e
    # so assim a guarda do jacobiano mede alguma coisa.
    tx = sitk.BSplineTransformInitializer(fixa, dom, order=3)
    m = sitk.ImageRegistrationMethod()
    m.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    m.SetMetricSamplingStrategy(m.RANDOM)
    m.SetMetricSamplingPercentage(float(amostra), seed=20260825)
    m.SetInterpolator(sitk.sitkLinear)
    m.SetOptimizerAsLBFGSB(gradientConvergenceTolerance=1e-5,
                           numberOfIterations=int(passos),
                           maximumNumberOfCorrections=5,
                           maximumNumberOfFunctionEvaluations=int(avaliacoes))
    m.SetInitialTransform(tx, inPlace=True)
    if inicial is not None:
        m.SetMovingInitialTransform(inicial)
    if mascara is not None:
        import numpy as np
        mk = sitk.GetImageFromArray(np.asarray(mascara, dtype=np.uint8))
        mk.CopyInformation(fixa)
        m.SetMetricFixedMask(mk)
    m.SetShrinkFactorsPerLevel([1])
    m.SetSmoothingSigmasPerLevel([0.0])
    m.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    if prog is not None:
        m.AddCommand(sitk.sitkIterationEvent,
                     lambda: prog(u"deformável", m.GetOptimizerIteration(),
                                  m.GetMetricValue()))
    m.Execute(fixa, movel)
    return tx


def compor(rigida, deformavel):
    sitk = _sitk()
    c = sitk.CompositeTransform(3)
    if rigida is not None:
        c.AddTransform(rigida)
    if deformavel is not None:
        c.AddTransform(deformavel)
    return c


def campo_de(transformada, referencia):
    sitk = _sitk()
    f = sitk.TransformToDisplacementFieldFilter()
    f.SetReferenceImage(referencia)
    f.SetOutputPixelType(sitk.sitkVectorFloat64)
    return f.Execute(transformada)


def aplicar(movel, transformada, referencia, fundo=None):
    sitk = _sitk()
    if fundo is None:
        fundo = fundo_de(movel)
    return sitk.Resample(movel, referencia, transformada, sitk.sitkLinear,
                         float(fundo), movel.GetPixelID())


def suporte(movel, transformada, referencia):
    import numpy as np
    sitk = _sitk()
    um = sitk.Image(movel.GetSize(), sitk.sitkUInt8)
    um.CopyInformation(movel)
    um = um + 1
    s = sitk.Resample(um, referencia, transformada,
                      sitk.sitkNearestNeighbor, 0, sitk.sitkUInt8)
    return sitk.GetArrayFromImage(s) > 0


def jacobiano(campo):
    import numpy as np
    sitk = _sitk()
    d = np.array(campo.GetDirection(), dtype=np.float64).reshape(3, 3)
    if np.allclose(d, np.eye(3), rtol=0.0, atol=1e-12):
        return sitk.DisplacementFieldJacobianDeterminant(campo)
    u = sitk.GetArrayFromImage(campo)
    ug = (u.reshape(-1, 3) @ np.linalg.inv(d).T).reshape(u.shape)
    g = sitk.GetImageFromArray(np.ascontiguousarray(ug, dtype=np.float64),
                               isVector=True)
    g.SetSpacing(campo.GetSpacing())
    g.SetOrigin(campo.GetOrigin())
    j = sitk.DisplacementFieldJacobianDeterminant(g)
    j.CopyInformation(campo)
    return j


def inverso(campo, passos=20, tol=0.05):
    sitk = _sitk()
    f = sitk.InvertDisplacementFieldImageFilter()
    f.SetMaximumNumberOfIterations(passos)
    f.SetMeanErrorToleranceThreshold(1e-3)
    f.SetMaxErrorToleranceThreshold(tol)
    f.EnforceBoundaryConditionOn()
    return f.Execute(campo)


def consistencia(campo, campo_inv):
    import numpy as np
    from scipy import ndimage
    sitk = _sitk()
    d = sitk.GetArrayFromImage(campo)
    di = sitk.GetArrayFromImage(campo_inv)
    dest = (np.indices(d.shape[:3], dtype=np.float32)
            + _desloc_em_indice(campo))
    res = np.array(d, dtype=np.float64, copy=True)
    # GUARDA: o inverso e lido por interpolacao trilinear no destino; o
    # vizinho mais proximo soma meio voxel de erro de arredondamento ao residuo.
    for k in range(3):
        res[..., k] += ndimage.map_coordinates(
            np.ascontiguousarray(di[..., k]), dest, order=1, mode="nearest")
    return np.sqrt((res ** 2).sum(axis=-1))


def _para_indice(campo):
    import numpy as np
    d = np.array(campo.GetDirection(), dtype=np.float64).reshape(3, 3)
    esp = np.array(campo.GetSpacing(), dtype=np.float64)
    return np.diag(1.0 / esp) @ np.linalg.inv(d)


def _desloc_em_indice(campo):
    import numpy as np
    sitk = _sitk()
    d = sitk.GetArrayFromImage(campo)
    m = _para_indice(campo)
    idx = d.reshape(-1, 3) @ m.T
    idx = idx.reshape(d.shape)
    return np.stack([idx[..., 2], idx[..., 1], idx[..., 0]],
                    axis=0).astype(np.float32)


def magnitude(campo):
    import numpy as np
    sitk = _sitk()
    d = sitk.GetArrayFromImage(campo)
    return np.sqrt((d ** 2).sum(axis=-1))


def _pct(a, q):
    import numpy as np
    return float(np.percentile(a, q))


def laudo(campo, campo_inv=None, dentro=None, jac=None, cobertura=None,
          malha=None, consist=None, ar=None):
    import numpy as np
    if jac is None:
        jac = jacobiano(campo)
    sitk = _sitk()
    j = sitk.GetArrayFromImage(jac)
    mag = magnitude(campo)

    if dentro is None:
        m = np.ones(j.shape, dtype=bool)
    else:
        m = np.asarray(dentro, dtype=bool)
        if m.shape != j.shape:
            m = np.ones(j.shape, dtype=bool)

    n = int(m.sum())
    jv = j[m] if n else j.ravel()
    mv = mag[m] if n else mag.ravel()

    dobras = int((jv < JAC_DOBRA).sum())
    r = {
        "n_voxels": n,
        "jac_min": float(jv.min()), "jac_max": float(jv.max()),
        "jac_p01": _pct(jv, 1), "jac_p99": _pct(jv, 99),
        "jac_mediana": float(np.median(jv)),
        "dobras": dobras,
        "dobras_parte": (100.0 * dobras / max(1, jv.size)),
        "magros": int((jv < JAC_MAGRO).sum()),
        "gordos": int((jv > JAC_GORDO).sum()),
        "desloc_mediana": float(np.median(mv)),
        "desloc_p95": _pct(mv, 95), "desloc_max": float(mv.max()),
        "consist_mediana": None, "consist_p95": None, "consist_max": None,
        "cobertura_parte": (None if cobertura is None
                            else 100.0 * float(cobertura)),
        "malha": (None if malha is None else int(malha)),
        "ar": ar,
    }
    c = consist
    if c is None and campo_inv is not None:
        c = consistencia(campo, campo_inv)
    if c is not None and np.shape(c) == j.shape:
        cv = c[m] if n else c.ravel()
        r["consist_mediana"] = float(np.median(cv))
        r["consist_p95"] = _pct(cv, 95)
        r["consist_max"] = float(cv.max())

    r["veredito"], r["porques"] = _veredito(r)
    return r


def _veredito(r):
    porques = []
    pior = 0
    if r["dobras"] > 0:
        pior = 2
        porques.append(
            u"O campo DOBRA em %d voxels (%.3f%%): jacobiano negativo é "
            u"tecido passando por dentro de si mesmo, e isso não acontece em "
            u"paciente." % (r["dobras"], r["dobras_parte"]))
    if r["jac_min"] < JAC_MAGRO:
        pior = max(pior, 1)
        if r["jac_min"] > 0.0:
            porques.append(
                u"Compressão de até %.2fx num ponto (jacobiano %.3f). Abaixo "
                u"de %.2f quase sempre é o otimizador casando histograma."
                % (1.0 / r["jac_min"], r["jac_min"], JAC_MAGRO))
        else:
            porques.append(
                u"Jacobiano mínimo de %.3f. Abaixo de %.2f quase sempre é o "
                u"otimizador casando histograma." % (r["jac_min"], JAC_MAGRO))
    if r["jac_max"] > JAC_GORDO:
        pior = max(pior, 1)
        porques.append(
            u"Expansão de até %.2fx num ponto (jacobiano %.2f)."
            % (r["jac_max"], r["jac_max"]))
    if r["consist_p95"] is not None and r["consist_p95"] > CONSIST_P95_MM:
        pior = max(pior, 1)
        porques.append(
            u"A ida e a volta não fecham: %.2f mm no p95, contra %.1f mm de "
            u"tolerância deste aplicativo."
            % (r["consist_p95"], CONSIST_P95_MM))
    if r["desloc_max"] > DESLOC_MAX_MM:
        pior = max(pior, 1)
        porques.append(
            u"Deslocamento de %.0f mm num ponto. Pode ser real (bexiga, "
            u"perda de peso), e pode ser o campo fugindo — olhar." %
            r["desloc_max"])
    cob = r.get("cobertura_parte")
    if cob is not None and cob < COBERTURA_MIN_PARTE:
        pior = max(pior, 1)
        porques.append(
            u"A móvel cobre só %.0f%% do corpo da fixa, e o laudo mede só "
            u"ali: fora dessa região o campo foi extrapolado, sem imagem "
            u"contra a qual errar. Abaixo de %.0f%% este aplicativo não "
            u"chama isso de laudo da fusão." % (cob, COBERTURA_MIN_PARTE))
    ar = r.get("ar") or {}
    if ar.get("aplica") and ar.get("regioes"):
        pior = max(pior, 1)
        g = ar["regioes"][0]
        porques.append(
            u"Ar contra tecido em %.1f cm³ (%d %s): onde uma série tem gás "
            u"e a outra tem tecido no mesmo ponto (reto, alça, estômago), "
            u"nenhuma deformação é fisicamente correta — o campo inventa a "
            u"correspondência. A maior fica nos cortes %d a %d, com gás na "
            u"%s." % (ar["cm3"], ar["n"],
                      u"região" if ar["n"] == 1 else u"regiões",
                      g["corte_de"], g["corte_ate"],
                      u"fixa" if g["gas_na"] == "fixa" else u"móvel"))
    mal = r.get("malha")
    if r["dobras"] > 0 and mal is not None and int(mal) > MALHA_MENOS_LIVRE:
        porques.append(
            u"Menos liberdade costuma desfazer a dobra: refaça com a "
            u"malha %d, ou só com a rígida." % MALHA_MENOS_LIVRE)
    if not porques:
        porques.append(
            u"Sem dobra, sem compressão extrema e com a ida-e-volta fechando "
            u"dentro da tolerância. Isto diz que a TRANSFORMAÇÃO é plausível "
            u"— não que o alinhamento esteja certo onde importa.")
    return VEREDITOS[pior], porques


TECIDO_HU = -200.0
AR_MIN_CM3 = 1.0
AR_TETO_REGIOES = 5


def levar_mascara(mascara, movel, transformada, referencia):
    import numpy as np
    sitk = _sitk()
    m = sitk.GetImageFromArray(np.asarray(mascara, dtype=np.uint8))
    m.CopyInformation(movel)
    s = sitk.Resample(m, referencia, transformada, sitk.sitkNearestNeighbor,
                      0, sitk.sitkUInt8)
    return sitk.GetArrayFromImage(s) > 0


def ar_contra_tecido(fixa, fundida, dentro, corpo_movel=None):
    import numpy as np
    from scipy import ndimage
    sitk = _sitk()
    a = sitk.GetArrayViewFromImage(fixa)
    b = sitk.GetArrayViewFromImage(fundida)
    onde = np.asarray(dentro, dtype=bool)
    if onde.shape != a.shape or a.shape != b.shape:
        return {"aplica": False}
    gas_b = b < LIMIAR_AR_HU
    # GUARDA: gas da movel e o de DENTRO do corpo dela; sem isto o ar de fora
    # que a borda da pele desalinhada traz vira cavidade.
    if corpo_movel is not None and np.shape(corpo_movel) == a.shape:
        gas_b = gas_b & np.asarray(corpo_movel, dtype=bool)
    esp = fixa.GetSpacing()
    cm3_por_voxel = float(esp[0] * esp[1] * esp[2]) / 1000.0
    regioes = []
    for lado, m in (("fixa", (a < LIMIAR_AR_HU) & (b > TECIDO_HU)),
                    ("movel", gas_b & (a > TECIDO_HU))):
        # GUARDA: a abertura tira a casca de um voxel que todo alinhamento
        # deixa na borda do ar; so sobra o que tem volume.
        m = ndimage.binary_opening(m & onde, iterations=1)
        rot, n = ndimage.label(m)
        if not n:
            continue
        tam = ndimage.sum(m, rot, range(1, n + 1))
        caixas = ndimage.find_objects(rot)
        for i in range(n):
            cm3 = float(tam[i]) * cm3_por_voxel
            if cm3 < AR_MIN_CM3 or caixas[i] is None:
                continue
            z = caixas[i][0]
            regioes.append({"gas_na": lado, "cm3": round(cm3, 2),
                            "corte_de": int(z.start) + 1,
                            "corte_ate": int(z.stop)})
    regioes.sort(key=lambda g: (-g["cm3"], g["corte_de"]))
    return {"aplica": True, "n": len(regioes),
            "cm3": round(sum(g["cm3"] for g in regioes), 2),
            "regioes": regioes[:AR_TETO_REGIOES]}


def mascara_corpo(img, limiar=None):
    import numpy as np
    from scipy import ndimage
    sitk = _sitk()
    a = sitk.GetArrayFromImage(img)
    hu = eh_hu(a)
    if limiar is None:
        limiar = (LIMIAR_CORPO_HU if hu
                  else FRACAO_CORPO_SINAL * float(np.percentile(a, 99)))
    m = a > limiar
    if not hu:
        p = 3
        m = ndimage.binary_closing(np.pad(m, p, mode="edge"),
                                   iterations=2)[p:-p, p:-p, p:-p]
    rot, n = ndimage.label(m)
    if n > 1:
        tam = ndimage.sum(m, rot, range(1, n + 1))
        m = rot == (int(np.argmax(tam)) + 1)
    m = ndimage.binary_fill_holes(m)
    if not hu:
        for k in range(m.shape[0]):
            m[k] = ndimage.binary_fill_holes(m[k])
    return m


def janela_de(img, dentro=None):
    import numpy as np
    if eh_hu(img):
        return (40.0, 400.0)
    sitk = _sitk()
    a = sitk.GetArrayFromImage(img)
    v = a[dentro] if (dentro is not None and np.shape(dentro) == a.shape
                      and np.any(dentro)) else a.ravel()
    lo, hi = (float(x) for x in np.percentile(v, (1.0, 99.5)))
    if not hi > lo:
        hi = lo + 1.0
    return ((lo + hi) / 2.0, hi - lo)


def xadrez(a, b, blocos=8):
    sitk = _sitk()
    f = sitk.CheckerBoardImageFilter()
    f.SetCheckerPattern([blocos, blocos, blocos])
    return f.Execute(sitk.Cast(a, sitk.sitkFloat32),
                     sitk.Cast(b, sitk.sitkFloat32))


def grade_deformada(campo, corte, passo=10, amostra=2):
    import numpy as np
    di = _desloc_em_indice(campo)
    nz, ny, nx = di.shape[1:]
    z = max(0, min(nz - 1, int(corte)))
    dx, dy = di[2, z], di[1, z]
    linhas = []
    for y in range(0, ny, passo):
        xs = list(range(0, nx, amostra))
        linhas.append([(x + float(dx[y, x]), y + float(dy[y, x]))
                       for x in xs])
    for x in range(0, nx, passo):
        ys = list(range(0, ny, amostra))
        linhas.append([(x + float(dx[y, x]), y + float(dy[y, x]))
                       for y in ys])
    return linhas


def setas(campo, corte, passo=12, escala=1.0):
    import numpy as np
    sitk = _sitk()
    d = sitk.GetArrayFromImage(campo)
    di = _desloc_em_indice(campo)
    nz, ny, nx = d.shape[:3]
    z = max(0, min(nz - 1, int(corte)))
    mm = np.sqrt((d[z] ** 2).sum(axis=-1))
    fora = []
    for y in range(passo // 2, ny, passo):
        for x in range(passo // 2, nx, passo):
            if mm[y, x] < 0.25:
                continue
            fora.append((x, y,
                         x + escala * float(di[2, z, y, x]),
                         y + escala * float(di[1, z, y, x]),
                         float(mm[y, x])))
    return fora


def fundir(fixa, movel, esp_mm=2.0, malha=8, prog=None, so_rigido=False):
    def diga(t):
        if prog:
            prog(t, -1, 0.0)

    diga(u"preparando")
    hu = (eh_hu(fixa), eh_hu(movel))
    fundo_m = fundo_de(movel)
    f = preparar(fixa, esp_mm)
    m = preparar(movel, esp_mm)

    diga(u"rígido")
    ini, inicio, valores = inicio_do_rigido(f, m)
    tr = registrar_rigido(f, m, prog=prog, inicial=ini)

    td = None
    metrica_no_corpo = False
    if not so_rigido:
        diga(u"deformável")
        mk = mascara_da_metrica(f, m, tr)
        metrica_no_corpo = mk is not None
        td = registrar_deformavel(f, m, tr, malha=malha, prog=prog,
                                  mascara=mk)

    tudo = compor(tr, td)
    diga(u"campo")
    c = campo_de(tudo, f)
    diga(u"inverso")
    try:
        ci = inverso(c)
    except Exception:
        ci = None
    consist = None
    if ci is not None:
        try:
            consist = consistencia(c, ci).astype("float32")
        except Exception:
            consist = None
    diga(u"reamostrando")
    fund = aplicar(m, tudo, f, fundo=fundo_m)
    rig = aplicar(m, compor(tr, None), f, fundo=fundo_m)
    diga(u"laudo")
    try:
        corpo = mascara_corpo(f)
    except Exception:
        corpo = None
    try:
        sup = suporte(m, tudo, f)
    except Exception:
        sup = None
    dentro, cobertura = corpo, None
    if sup is not None:
        if corpo is not None and corpo.shape == sup.shape:
            dentro = corpo & sup
            cobertura = float(dentro.sum()) / max(1.0, float(corpo.sum()))
        else:
            dentro = sup
    try:
        corpo_m = mascara_corpo(m)
    except Exception:
        corpo_m = None
    ar = {"aplica": False}
    # GUARDA: fora do suporte a fundida e fundo (-1024), que passaria por gas.
    if all(hu) and sup is not None and dentro is not None:
        try:
            levado = (None if corpo_m is None
                      else levar_mascara(corpo_m, m, tudo, f))
            ar = ar_contra_tecido(f, fund, dentro, corpo_movel=levado)
        except Exception:
            ar = {"aplica": False}
    jac = jacobiano(c)
    l = laudo(c, ci, dentro=dentro, jac=jac, cobertura=cobertura,
              malha=(None if so_rigido else malha), consist=consist, ar=ar)
    l["inicio_rigido"] = inicio
    l["metrica_no_corpo"] = metrica_no_corpo
    try:
        jan_m = janela_de(m, corpo_m)
    except Exception:
        jan_m = janela_de(m)
    janelas = {"fixa": janela_de(f, corpo), "movel": jan_m}
    return {"fixa": f, "movel": m, "movel_rig": rig, "fundida": fund,
            "campo": c, "transformada": tudo, "laudo": l, "jac": jac,
            "hu": hu, "janelas": janelas, "inicio": inicio,
            "inicio_valores": valores, "cobertura": cobertura,
            "dentro": dentro, "consist": consist,
            "so_rigido": bool(so_rigido)}
