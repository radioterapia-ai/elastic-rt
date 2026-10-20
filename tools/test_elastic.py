# -*- coding: utf-8 -*-
import io
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

AQUI = os.path.dirname(os.path.abspath(__file__))


def pasta_app(aqui):
    for c in (os.path.join(aqui, "..", "app"), os.path.join(aqui, "..")):
        if os.path.exists(os.path.join(c, "radai_watcher.py")):
            return os.path.abspath(c)
    return os.path.abspath(os.path.join(aqui, "..", "app"))


APP = pasta_app(AQUI)
sys.path.insert(0, APP)

import tempfile as _tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _cleanup
import _componentes
_cleanup.adotar_prefixo('radai_ac_elastic')
os.environ["RADAI_CALIB_DIR"] = _tempfile.mkdtemp(prefix="radai_ac_elastic_")


VERBOSO = "-v" in sys.argv
_RES = []


def checar(nome, ok, detalhe=""):
    _RES.append((nome, bool(ok), detalhe))
    if VERBOSO or not ok:
        print("  %s  %s%s" % ("OK   " if ok else "FALHA", nome,
                              ("  [%s]" % detalhe) if detalhe else ""))
    return bool(ok)


def secao(t):
    print(u"\n── %s %s" % (t, u"─" * max(0, 58 - len(t))))


def fonte(nome):
    return io.open(_componentes.fonte("app/" + nome), encoding="utf-8",
                   errors="replace").read()


def sem_docstring(texto):
    import ast
    t = "\n".join(l for l in texto.splitlines()
                  if not l.lstrip().startswith("#")
                  and not l.lstrip().startswith("//"))
    try:
        arv = ast.parse(t)
    except Exception:
        return t
    linhas = t.splitlines()
    for no in ast.walk(arv):
        if isinstance(no, (ast.Module, ast.ClassDef, ast.FunctionDef,
                           ast.AsyncFunctionDef)):
            c = no.body[0] if no.body else None
            if (isinstance(c, ast.Expr) and isinstance(c.value, ast.Constant)
                    and isinstance(c.value.value, str)):
                for k in range(c.lineno - 1,
                               min(getattr(c, "end_lineno", c.lineno),
                                   len(linhas))):
                    linhas[k] = ""
    return "\n".join(linhas)


def grade(nz=24, ny=32, nx=32, esp=2.0, direcao=None):
    import SimpleITK as sitk
    import numpy as np
    img = sitk.GetImageFromArray(np.zeros((nz, ny, nx), dtype=np.float32))
    img.SetSpacing((esp, esp, esp))
    img.SetOrigin((-nx * esp / 2.0, -ny * esp / 2.0, -nz * esp / 2.0))
    if direcao:
        img.SetDirection(direcao)
    return img


def campo_de(ref, fn):
    import SimpleITK as sitk
    import numpy as np
    nx, ny, nz = ref.GetSize()
    z, y, x = np.mgrid[0:nz, 0:ny, 0:nx].astype(np.float64)
    d = fn(z, y, x)
    c = sitk.GetImageFromArray(np.ascontiguousarray(d), isVector=True)
    c.CopyInformation(ref)
    return c


def teste_a_medida_mede():
    secao(u"a medida mede: campo conhecido, número conhecido")
    import numpy as np
    import radai_elastic as E

    ref = grade()
    esp = ref.GetSpacing()[0]

    c = campo_de(ref, lambda z, y, x: np.stack(
        [np.full(x.shape, 7.0), np.zeros(x.shape), np.zeros(x.shape)],
        axis=-1))
    l = E.laudo(c, None)
    checar(u"translação pura: jacobiano 1,000",
           abs(l["jac_min"] - 1.0) < 1e-6 and abs(l["jac_max"] - 1.0) < 1e-6,
           u"%.6f..%.6f" % (l["jac_min"], l["jac_max"]))
    checar(u"e o deslocamento é os 7 mm pedidos",
           abs(l["desloc_mediana"] - 7.0) < 1e-6,
           u"%.4f mm" % l["desloc_mediana"])
    checar(u"e ela PASSA", l["veredito"] == "passa", l["veredito"])

    k = 0.2
    c = campo_de(ref, lambda z, y, x: np.stack(
        [k * x * esp, np.zeros(x.shape), np.zeros(x.shape)], axis=-1))
    l = E.laudo(c, None)
    import SimpleITK as sitk
    j = sitk.GetArrayFromImage(E.jacobiano(c))[2:-2, 2:-2, 2:-2]
    checar(u"expansão de 1,2x em x devolve jacobiano 1,200",
           abs(float(np.median(j)) - (1.0 + k)) < 1e-3,
           u"mediana %.4f" % float(np.median(j)))

    k = -0.3
    c = campo_de(ref, lambda z, y, x: np.stack(
        [k * x * esp, np.zeros(x.shape), np.zeros(x.shape)], axis=-1))
    j = sitk.GetArrayFromImage(E.jacobiano(c))[2:-2, 2:-2, 2:-2]
    checar(u"compressão de 0,7x devolve jacobiano 0,700",
           abs(float(np.median(j)) - 0.7) < 1e-3,
           u"mediana %.4f" % float(np.median(j)))


def teste_o_reprova_acende():
    secao(u"o `reprova` acende: um campo que DOBRA")
    import numpy as np
    import radai_elastic as E

    ref = grade()
    esp = ref.GetSpacing()[0]

    k = -1.6
    c = campo_de(ref, lambda z, y, x: np.stack(
        [k * x * esp, np.zeros(x.shape), np.zeros(x.shape)], axis=-1))
    l = E.laudo(c, None)
    checar(u"jacobiano NEGATIVO num campo que dobra", l["jac_min"] < 0.0,
           u"%.3f" % l["jac_min"])
    checar(u"e ele conta os voxels que dobram", l["dobras"] > 0,
           u"%d (%.1f%%)" % (l["dobras"], l["dobras_parte"]))
    checar(u"e o veredito é REPROVA", l["veredito"] == "reprova",
           l["veredito"])
    checar(u"e o porquê fala em dobra",
           any(u"DOBRA" in p for p in l["porques"]),
           l["porques"][0][:60])

    k = -0.95
    c = campo_de(ref, lambda z, y, x: np.stack(
        [k * x * esp, np.zeros(x.shape), np.zeros(x.shape)], axis=-1))
    l = E.laudo(c, None)
    checar(u"compressão de 20x sem dobrar dá ATENÇÃO, não reprova",
           l["veredito"] == "atencao" and l["dobras"] == 0,
           u"%s · jmin %.3f · dobras %d"
           % (l["veredito"], l["jac_min"], l["dobras"]))

    checar(u"os três vereditos são declarados",
           E.VEREDITOS == ("passa", "atencao", "reprova"), str(E.VEREDITOS))
    checar(u"e o limiar de dobra é ZERO, e não uma escolha",
           E.JAC_DOBRA == 0.0, str(E.JAC_DOBRA))

    codigo = fonte("radai_elastic.py")
    checar(u"o motor deformável é B-spline (que PODE dobrar)",
           "BSplineTransformInitializer" in codigo)
    checar(u"e não é Demons difeomórfico (que não pode)",
           "Diffeomorphic" not in codigo and "DemonsRegistration" not in codigo)
    checar(u"e o GUARDA: diz por que, no ponto",
           any(u"GUARDA:" in l and u"difeomorfico" in l
               for l in codigo.splitlines()))


def teste_a_ida_e_volta():
    secao(u"a ida-e-volta: a única medida que não depende de nada externo")
    import numpy as np
    import radai_elastic as E

    ref = grade(nz=28, ny=40, nx=40)
    c = campo_de(ref, lambda z, y, x: np.stack(
        [3.0 * np.sin(y / 7.0), 2.0 * np.cos(x / 9.0), np.zeros(x.shape)],
        axis=-1))
    ci = E.inverso(c)
    r = E.consistencia(c, ci)
    miolo = r[3:-3, 3:-3, 3:-3]
    checar(u"campo suave fecha a ida-e-volta no miolo",
           float(np.percentile(miolo, 95)) < 1.0,
           u"p95 %.3f mm" % float(np.percentile(miolo, 95)))

    l = E.laudo(c, ci)
    checar(u"e o laudo traz os três números da consistência",
           all(l[k] is not None
               for k in ("consist_mediana", "consist_p95", "consist_max")))
    checar(u"sem campo inverso, eles ficam NULOS e não zerados",
           E.laudo(c, None)["consist_p95"] is None)


def teste_a_direcao_obliqua():
    secao(u"direção oblíqua: a conversão passa pela matriz")
    import math
    import numpy as np
    import radai_elastic as E

    a = math.radians(20.0)
    ref = grade(direcao=(math.cos(a), -math.sin(a), 0.0,
                         math.sin(a), math.cos(a), 0.0, 0.0, 0.0, 1.0))
    c = campo_de(ref, lambda z, y, x: np.stack(
        [np.full(x.shape, 10.0), np.zeros(x.shape), np.zeros(x.shape)],
        axis=-1))
    i = E._desloc_em_indice(c)
    esp = ref.GetSpacing()[0]
    checar(u"10 mm em x físico NÃO viram 10/espaçamento no índice x",
           abs(float(i[2, 0, 0, 0]) - 10.0 / esp) > 0.1,
           u"idx dx %.4f contra o atalho %.4f"
           % (float(i[2, 0, 0, 0]), 10.0 / esp))
    checar(u"e a componente y do índice deixa de ser zero",
           abs(float(i[1, 0, 0, 0])) > 0.1, u"idx dy %.4f"
           % float(i[1, 0, 0, 0]))
    esperado = np.diag([1.0 / esp] * 3) @ np.linalg.inv(
        np.array(ref.GetDirection()).reshape(3, 3)) @ np.array([10.0, 0, 0])
    checar(u"e a conta bate com espaçamento⁻¹ · D⁻¹ · mm",
           abs(float(i[2, 0, 0, 0]) - esperado[0]) < 1e-5
           and abs(float(i[1, 0, 0, 0]) - esperado[1]) < 1e-5,
           u"%.7f vs %.7f · %.7f vs %.7f"
           % (i[2, 0, 0, 0], esperado[0], i[1, 0, 0, 0], esperado[1]))

    ref2 = grade()
    c2 = campo_de(ref2, lambda z, y, x: np.stack(
        [np.full(x.shape, 10.0), np.zeros(x.shape), np.zeros(x.shape)],
        axis=-1))
    i2 = E._desloc_em_indice(c2)
    checar(u"e com direção identidade ela devolve o atalho",
           abs(float(i2[2, 0, 0, 0]) - 10.0 / esp) < 1e-5)


def teste_a_mascara_do_corpo():
    secao(u"a estatística é do CORPO, e não do ar")
    import numpy as np
    import SimpleITK as sitk
    import radai_elastic as E

    nz, ny, nx = 20, 40, 40
    v = np.full((nz, ny, nx), -1000.0, dtype=np.float32)
    v[4:16, 10:30, 10:30] = 40.0
    img = sitk.GetImageFromArray(v)
    img.SetSpacing((2.0, 2.0, 2.0))
    m = E.mascara_corpo(img)
    checar(u"a máscara acha o corpo e não o ar",
           0.05 < m.sum() / float(m.size) < 0.5,
           u"%.1f%% do volume" % (100.0 * m.sum() / m.size))

    c = campo_de(img, lambda z, y, x: np.stack(
        [np.where((x < 8) | (x > 32), 60.0, 1.0), np.zeros(x.shape),
         np.zeros(x.shape)], axis=-1))
    l_todo = E.laudo(c, None, dentro=None)
    l_corpo = E.laudo(c, None, dentro=m)
    checar(u"sem máscara, o p95 é o do AR",
           l_todo["desloc_p95"] > 30.0,
           u"%.1f mm" % l_todo["desloc_p95"])
    checar(u"com máscara, ele é o do corpo",
           l_corpo["desloc_p95"] < 10.0,
           u"%.1f mm" % l_corpo["desloc_p95"])
    checar(u"e o laudo diz quantos voxels entraram na conta",
           l_corpo["n_voxels"] == int(m.sum()),
           u"%d" % l_corpo["n_voxels"])


def teste_a_trava_da_imagem():
    secao(u"a trava: a imagem não sai sem o laudo do campo")
    import radai_elastic_screen as T

    for v in T.DEPENDEM_DO_CAMPO:
        try:
            T.conferir_laudo({"r": {}}, v)
            checar(u"«%s» sem laudo é RECUSADA" % v, False, u"passou")
        except T.SemLaudo:
            checar(u"«%s» sem laudo é RECUSADA" % v, True)
    for v in ("fixa", "rigida", "xadrez_rig"):
        try:
            ok = T.conferir_laudo({"r": {}}, v)
            checar(u"«%s» não depende do campo e passa" % v, ok)
        except T.SemLaudo:
            checar(u"«%s» não depende do campo e passa" % v, False)
    checar(u"e com laudo a vista derivada passa",
           T.conferir_laudo({"r": {"laudo": {"veredito": "passa"}}},
                            "fundida"))
    try:
        T.conferir_laudo({"r": {"laudo": {"veredito": ""}}}, "fundida")
        checar(u"laudo sem veredito não conta como laudo", False)
    except T.SemLaudo:
        checar(u"laudo sem veredito não conta como laudo", True)

    codigo = sem_docstring(fonte("radai_elastic_screen.py"))
    checar(u"`conferir_laudo` é chamada por quem monta o corte",
           re.search(r"def _plano\([^)]*\):\s*\n\s*conferir_laudo\(", codigo)
           is not None)
    checar(u"e a rota da imagem passa por `_plano`",
           re.search(r"def _corte\(.*?_plano\(", codigo, re.S) is not None)
    checar(u"e a recusa vira 409, e não 500",
           "SemLaudo" in codigo and "status_code=409" in codigo)

    livres = {"fixa", "rigida", "xadrez_rig"}
    checar(u"toda vista fora das três livres exige laudo",
           set(T.VISTAS) - livres == set(T.DEPENDEM_DO_CAMPO),
           u"órfãs: %s" % sorted(set(T.VISTAS) - livres
                                 - set(T.DEPENDEM_DO_CAMPO)))
    checar(u"e toda vista tem janela declarada",
           set(T.VISTAS) <= set(T.JANELAS),
           u"sem janela: %s" % sorted(set(T.VISTAS) - set(T.JANELAS)))
    checar(u"e toda vista tem rótulo na tela",
           set(T.VISTAS) == set(r[0] for r in T.ROTULOS))


def teste_nao_propaga_e_nao_exporta():
    secao(u"a fronteira: não propaga contorno, e não exporta")
    import radai_elastic as E
    import radai_elastic_screen as T

    codigo = sem_docstring(fonte("radai_elastic.py"))
    tela = sem_docstring(fonte("radai_elastic_screen.py"))

    for proibido in ("build_rtstruct", "RTSTRUCT", "rt_utils", "radai_rt",
                     "ROIContour", "StructureSet", "gravar_rs"):
        checar(u"o motor não escreve `%s`" % proibido, proibido not in codigo)
        checar(u"e a tela também não", proibido not in tela)
    for proibido in ("toBlob", "toDataURL", "download", "attachment",
                     "content-disposition", "createObjectURL", "nii.gz",
                     "WriteImage"):
        checar(u"nada exporta `%s`" % proibido,
               proibido.lower() not in tela.lower()
               and proibido.lower() not in codigo.lower())

    pag = T.pagina()
    for frase, rot in ((E.NAO_PROPAGA, u"não propaga contorno"),
                       (E.REFERENCIA_E_NOSSA, u"a referência é nossa"),
                       (E.LIMIAR_E_NOSSO, u"o limiar é nosso"),
                       (E.SEM_APROVACAO, u"sugestão não aprovada")):
        checar(u"a tela DIZ: %s" % rot, frase[:40] in pag)
    checar(u"e ela cita o TG-132 no arquivo do motor",
           "TG-132" in fonte("radai_elastic.py"))
    import json as _json
    _bib = _json.loads(fonte("data/bibliography.json"))
    _brock = [a for a in _bib.get("artigos") or [] if a.get("id") == "brock2017"]
    checar(u"com o DOI, e não só o nome: a bibliografia amarra o TG-132 ao "
           u"laudo do motor",
           bool(_brock) and _brock[0].get("doi") == "10.1002/mp.12256"
           and "app/radai_elastic.py::laudo" in (_brock[0].get("influencia")
                                                 or []))


def teste_nada_e_detectado():
    secao(u"nada é detectado, nada é classificado")
    codigo = sem_docstring(fonte("radai_elastic.py"))
    tela = sem_docstring(fonte("radai_elastic_screen.py"))
    for p in ("nodule", "nodulo", "lesion", "lesao", "tumor", "malign",
              "suspeit", "candidat", "detect", "classific", "probabilidade"):
        checar(u"o motor não fala em `%s`" % p, p not in codigo.lower())
        checar(u"e a tela não fala em `%s`" % p, p not in tela.lower())
    checar(u"e não há modelo nem peso neste módulo",
           "torch" not in codigo and "state_dict" not in codigo
           and "model.pt" not in codigo)


def teste_o_caminho_nao_viaja_em_get():
    secao(u"o caminho do paciente não viaja em GET")
    tela = fonte("radai_elastic_screen.py")
    gets = re.findall(r"@app\.get\(\"([^\"]+)\"\)\s*\n\s*(?:async )?def "
                      r"\w+\(([^)]*)\)", tela)
    checar(u"há rotas GET para conferir", len(gets) >= 3, str(len(gets)))
    for rota, args in gets:
        checar(u"«%s» não recebe caminho" % rota,
               not re.search(r"\b(pasta|caminho|dir|path|sdir)\b", args),
               args.strip()[:60])
    checar(u"e a lista de séries é POST",
           '@app.post("/api/elastic/series")' in tela)
    checar(u"e a fusão também",
           '@app.post("/api/elastic/fundir")' in tela)
    checar(u"o id da tarefa é sorteado", "os.urandom" in tela)


def teste_uma_fusao_por_vez():
    secao(u"uma fusão por vez, e o resultado não vai para o disco")
    tela = sem_docstring(fonte("radai_elastic_screen.py"))
    checar(u"há trava de concorrência", "threading.Lock" in tela)
    checar(u"e a segunda fusão é recusada com explicação",
           u"em andamento" in tela)
    for proibido in ("open(", "makedirs", "shutil", "WriteImage", ".save("):
        checar(u"a tela não grava `%s`" % proibido, proibido not in tela)
    checar(u"e o GUARDA: diz que o resultado não vai para o disco",
           any(u"GUARDA:" in a and u"disco" in a + b
               for a, b in zip(fonte("radai_elastic_screen.py").splitlines(),
                               fonte("radai_elastic_screen.py").splitlines()[1:])))


def teste_o_cartao_nao_anuncia_obra_que_acabou():
    secao(u"o cartão do Elastic RT não anuncia obra encerrada")
    import radai_modules

    mod = radai_modules.MODULOS["elastic"]
    checar(u"o Elastic não tem mais selo de obra",
           not mod.get("selo"), repr(mod.get("selo")))
    checar(u"nem ajuda de selo pendurada",
           not mod.get("selo_ajuda"), repr(mod.get("selo_ajuda"))[:60])
    checar(u"e o estado não o impede de navegar",
           mod.get("estado", u"") not in radai_modules.NAO_NAVEGAM,
           repr(mod.get("estado")))

    nid = radai_modules.MODULOS["nidus"]
    checar(u"o Nidus RT também navega",
           nid.get("estado", u"") not in radai_modules.NAO_NAVEGAM,
           repr(nid.get("estado")))

    vasc = [f for f in radai_modules.FERRAMENTAS.get("recon3d", ())
            if f[0] == "recon_vascular"]
    checar(u"a reconstrução vascular está declarada", len(vasc) == 1,
           u"achei %d" % len(vasc))
    if vasc:
        estado = vasc[0][5] if len(vasc[0]) > 5 else u""
        checar(u"e ela abre na v8.4 (rota própria, sem etiqueta que trave)",
               vasc[0][3] == u"/recon3d/vascular"
               and not radai_modules.nao_navega(estado),
               u"%s" % (vasc[0],))


def teste_a_suite_conhece_o_modulo():
    secao(u"a suíte conhece o módulo, nos cinco lugares")
    import radai_menu
    import radai_modules
    import radai_breadcrumb
    import radai_ui

    checar(u"1· a trilha sabe onde ele mora",
           radai_breadcrumb.ARVORE.get("elastic", (None, None, None))[1]
           == "/elastic")
    checar(u"   e onde mora a ferramenta",
           radai_breadcrumb.ARVORE.get("elastic_fusao", (None, None, None))[1]
           == "/elastic/fusao")
    checar(u"2· o trilho o lista", "elastic" in radai_menu.MODULOS)
    checar(u"   e a home também", "elastic" in radai_menu.MODULOS_HOME)
    checar(u"3· o registro tem cor", "elastic" in radai_modules.CORES)
    checar(u"   identidade", "elastic" in radai_modules.MODULOS)
    checar(u"   ferramentas", "elastic" in radai_modules.FERRAMENTAS)
    checar(u"   balões", "elastic" in radai_modules.AJUDA)
    checar(u"   e a fronteira visível",
           "elastic" in radai_modules.SEM_EXPORTACAO)
    css = radai_ui.CSS if hasattr(radai_ui, "CSS") else fonte("radai_ui.py")
    checar(u"4· a cor existe nos DOIS temas",
           css.count("--mod-elastic:") >= 2,
           u"%d definições" % css.count("--mod-elastic:"))
    checar(u"   e a segunda cor também",
           css.count("--mod-elastic-b:") >= 2)
    checar(u"5· o painel monta a tela",
           '"radai_elastic_screen"' in fonte("radai_panel.py"))
    checar(u"   e o roteador serve a mini-página",
           '("elastic", "/elastic")' in fonte("radai_router.py"))

    import radai_porta
    linha = radai_porta.cartao("elastic", 4)
    checar(u"o cartão da porta aponta para /elastic",
           'href="/elastic"' in linha, linha[:70])
    checar(u"e não para a raiz", 'href="/"' not in linha)


def teste_a_tela_monta():
    secao(u"a tela monta, e o gabarito não deixa marcador solto")
    import radai_elastic_screen as T
    p = T.pagina()
    checar(u"a página tem corpo", len(p) > 4000, u"%d caracteres" % len(p))
    soltos = re.findall(r"@[A-Z0-9_]+@", p)
    checar(u"nenhum marcador @X@ sobrou", not soltos, str(soltos))
    checar(u"e desenha em SVG", "<svg" in p.lower())
    checar(u"sem canvas", "<canvas" not in p.lower())
    for v in T.VISTAS:
        checar(u"o botão da vista «%s» está lá" % v,
               'data-v="%s"' % v in p)
    checar(u"a barra de progresso existe", 'id="el-pct"' in p)
    checar(u"e o laudo tem lugar na tela", 'id="el-tab"' in p)

    checar(u"o CSS não tem `%%` escapado sobrando", "%%" not in p)

    ids = set(re.findall(r'id="([^"]+)"', p))
    procurados = set(re.findall(r"el\('([^']+)'\)", T.JS))
    checar(u"há âncoras de sobra para conferir", len(procurados) >= 10,
           u"%d" % len(procurados))
    checar(u"toda âncora que o JS procura existe na página",
           procurados <= ids,
           u"sem âncora: %s" % sorted(procurados - ids))


def teste_a_lista_acumula_pastas():
    secao(u"a lista de pastas SOMA, e não substitui")
    import json
    import radai_elastic_screen as T
    import radai_thumbnail

    A = u"C:\\EXAMES\\PAC01\\TC"
    B = u"C:\\EXAMES\\PAC01\\RM"

    def serie(uid, pasta, cortes=120, numero=2, esp=1.25):
        return {"uid": uid, "pasta": pasta, "cortes": cortes,
                "numero": numero, "espessura_mm": esp, "date": u"20240115",
                "curto": uid[-8:]}

    U1 = u"9.9.9.111111111.1001"
    U2 = u"9.9.9.111111111.2002"
    U3 = u"9.9.9.111111111.3003"

    l, av = T.acumular_pasta([], A, [serie(U1, A), serie(U2, A)],
                             radai_thumbnail.bilhete)
    checar(u"a primeira pasta entra com as séries dela",
           len(l) == 1 and len(l[0]["series"]) == 2,
           u"%d pasta(s), %d série(s)" % (len(l), len(l[0]["series"]) if l
                                          else 0))
    checar(u"e sem aviso nenhum", av == [], str(av))

    l, av = T.acumular_pasta(l, B, [serie(U3, B, cortes=90)],
                             radai_thumbnail.bilhete)
    tela = T.para_a_tela(l)
    checar(u"a segunda pasta SOMA em vez de substituir",
           len(tela["series"]) == 3, u"%d séries" % len(tela["series"]))
    checar(u"e as duas pastas aparecem na lista, numeradas 1 e 2",
           [p["n"] for p in tela["pastas"]] == [1, 2]
           and [p["pasta"] for p in tela["pastas"]] == [A, B],
           str([(p["n"], p["pasta"]) for p in tela["pastas"]]))
    checar(u"e cada pasta diz quantas séries trouxe",
           [p["series"] for p in tela["pastas"]] == [2, 1],
           str([p["series"] for p in tela["pastas"]]))

    checar(u"o rótulo de cada série diz de qual pasta ela veio",
           [r["rotulo"][:3] for r in tela["series"]] == [u"[1]", u"[1]",
                                                         u"[2]"],
           u" · ".join(r["rotulo"][:18] for r in tela["series"]))
    checar(u"e o rótulo continua trazendo cortes, espessura e data",
           all(u"cortes" in r["rotulo"] and u"mm" in r["rotulo"]
               and u"20240115" in r["rotulo"] for r in tela["series"]),
           tela["series"][0]["rotulo"])

    bruto = json.dumps(tela, ensure_ascii=False)
    checar(u"o UID inteiro não viaja para a tela",
           U1 not in bruto and U2 not in bruto and U3 not in bruto)
    checar(u"e os 8 últimos continuam viajando (é como se identifica)",
           U1[-8:] in bruto)
    checar(u"a série que sai tem só bilhete e rótulo",
           all(set(r) == {"b", "rotulo"} for r in tela["series"]),
           str(sorted(tela["series"][0])))

    p3, u3 = radai_thumbnail.resolver(tela["series"][2]["b"])
    checar(u"o bilhete da série da pasta 2 resolve para a pasta 2",
           p3 == B and u3 == U3, u"%s · …%s" % (p3, (u3 or u"")[-8:]))

    C = u"C:\\EXAMES\\COPIA"
    l2, av = T.acumular_pasta(l, C, [serie(U1, C)], radai_thumbnail.bilhete)
    checar(u"série repetida não entra duas vezes",
           len(T.para_a_tela(l2)["series"]) == 3,
           u"%d séries" % len(T.para_a_tela(l2)["series"]))
    checar(u"e a tela é AVISADA de que ela já estava",
           len(av) == 1 and u"já estava" in av[0], u" | ".join(av)[:90])
    checar(u"e a pasta nova entra na lista mesmo sem trazer série nova",
           len(l2) == 3 and T.para_a_tela(l2)["pastas"][2]["series"] == 0,
           u"%d pastas" % len(l2))

    l3, av = T.acumular_pasta(l, C, [serie(U1, C, cortes=64)],
                              radai_thumbnail.bilhete)
    checar(u"cópia com outra contagem de cortes é NOMEADA",
           len(av) == 1 and u"120" in av[0] and u"64" in av[0],
           u" | ".join(av)[:120])
    checar(u"e o aviso diz qual das duas ficou",
           u"incompleta" in av[0].lower(), av[0][:120])
    checar(u"a cópia MENOR não entra",
           len(T.para_a_tela(l3)["series"]) == 3
           and not [r for r in T.para_a_tela(l3)["series"]
                    if u"64 cortes" in r["rotulo"]],
           u" · ".join(r["rotulo"][:26] for r in T.para_a_tela(l3)["series"]))

    l3b, av = T.acumular_pasta(l, C, [serie(U1, C, cortes=200)],
                               radai_thumbnail.bilhete)
    t3b = T.para_a_tela(l3b)
    maiores = [r for r in t3b["series"] if u"200 cortes" in r["rotulo"]]
    checar(u"a cópia MAIOR substitui a truncada",
           len(maiores) == 1 and len(t3b["series"]) == 3,
           u" · ".join(r["rotulo"][:26] for r in t3b["series"]))
    checar(u"e o rótulo dela passa a dizer a pasta NOVA",
           maiores and maiores[0]["rotulo"].startswith(u"[3]"),
           maiores[0]["rotulo"][:26] if maiores else u"—")
    checar(u"e a contagem por pasta acompanha",
           [p["series"] for p in t3b["pastas"]] == [1, 1, 1],
           str([p["series"] for p in t3b["pastas"]]))
    checar(u"e a lista de quem chamou não foi alterada",
           [p["series"] for p in T.para_a_tela(l)["pastas"]] == [2, 1],
           str([p["series"] for p in T.para_a_tela(l)["pastas"]]))

    def cortes_de(lista):
        return sorted(int(re.search(r"(\d+) cortes", r["rotulo"]).group(1))
                      for r in T.para_a_tela(lista)["series"])

    ida, _x = T.acumular_pasta([], A, [serie(U1, A, cortes=120)],
                               radai_thumbnail.bilhete)
    ida, _x = T.acumular_pasta(ida, C, [serie(U1, C, cortes=200)],
                               radai_thumbnail.bilhete)
    volta, _x = T.acumular_pasta([], C, [serie(U1, C, cortes=200)],
                                 radai_thumbnail.bilhete)
    volta, _x = T.acumular_pasta(volta, A, [serie(U1, A, cortes=120)],
                                 radai_thumbnail.bilhete)
    checar(u"a ordem das pastas não muda qual cópia fica",
           cortes_de(ida) == [200] and cortes_de(volta) == [200],
           u"%s contra %s" % (cortes_de(ida), cortes_de(volta)))

    D = u"C:\\EXAMES\\ZIPADO"
    l7, av = T.acumular_pasta([], D, [serie(U1, D, cortes=64),
                                      serie(U1, D, cortes=120)],
                              radai_thumbnail.bilhete)
    t7 = T.para_a_tela(l7)
    checar(u"UID repetido na MESMA varredura entra uma vez só",
           len(t7["series"]) == 1
           and u"120 cortes" in t7["series"][0]["rotulo"],
           u" · ".join(r["rotulo"][:26] for r in t7["series"]))
    checar(u"e a pasta conta uma série, e não duas",
           t7["pastas"][0]["series"] == 1, str(t7["pastas"]))

    checar(u"a pasta já listada é achada pelo índice",
           T.indice_de_pasta(l, A) == 1 and T.indice_de_pasta(l, B) == 2
           and T.indice_de_pasta(l, u"C:\\OUTRA") == 0)
    checar(u"e ela é achada mesmo com barra e caixa diferentes",
           T.indice_de_pasta(l, u"c:\\exames\\pac01\\tc\\") == 1,
           str(T.indice_de_pasta(l, u"c:\\exames\\pac01\\tc\\")))
    l4, av = T.acumular_pasta(l, A, [serie(U1, A)], radai_thumbnail.bilhete)
    checar(u"acrescentar a MESMA pasta não duplica nada",
           len(l4) == 2 and len(T.para_a_tela(l4)["series"]) == 3,
           u"%d pastas · %d séries"
           % (len(l4), len(T.para_a_tela(l4)["series"])))
    checar(u"e ela diz que a pasta já está na lista",
           len(av) == 1 and u"já está na lista" in av[0], u" | ".join(av))

    l5, fora = T.tirar_pasta(l, 1)
    t5 = T.para_a_tela(l5)
    checar(u"tirar a pasta 1 leva as duas séries dela", len(t5["series"]) == 1,
           u"%d séries" % len(t5["series"]))
    checar(u"e devolve qual pasta saiu", fora == A, str(fora))
    checar(u"e a que sobrou é RENUMERADA para [1]",
           t5["pastas"][0]["n"] == 1 and t5["pastas"][0]["pasta"] == B
           and t5["series"][0]["rotulo"].startswith(u"[1]"),
           t5["series"][0]["rotulo"][:20])
    l6, fora = T.tirar_pasta(l, 9)
    checar(u"tirar pasta que não existe não apaga nada",
           len(T.para_a_tela(l6)["series"]) == 3 and fora is None,
           str(fora))

    vazia = T.para_a_tela([])
    checar(u"lista vazia devolve as duas chaves, vazias",
           vazia["pastas"] == [] and vazia["series"] == [], str(vazia))


SOP_DA_MODALIDADE = {"CT": "1.2.840.10008.5.1.4.1.1.2",
                     "MR": "1.2.840.10008.5.1.4.1.1.4",
                     "RTSTRUCT": "1.2.840.10008.5.1.4.1.1.481.3"}


def gravar_serie(pasta, uid, n=10, modalidade="CT", prefixo="IM",
                 data="20240115", numero=3, esp=2.5):
    import numpy as np
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid
    os.makedirs(pasta, exist_ok=True)
    sop = SOP_DA_MODALIDADE[modalidade]
    for i in range(n):
        meta = FileMetaDataset()
        meta.MediaStorageSOPClassUID = sop
        meta.MediaStorageSOPInstanceUID = generate_uid()
        meta.TransferSyntaxUID = ExplicitVRLittleEndian
        ds = FileDataset(None, {}, file_meta=meta, preamble=b"\0" * 128)
        ds.SOPClassUID = sop
        ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
        ds.Modality = modalidade
        ds.SeriesInstanceUID = uid
        ds.StudyInstanceUID = u"9.9.9.1"
        ds.PatientID = u"FANTOMA"
        ds.SeriesNumber = numero
        ds.InstanceNumber = i + 1
        ds.SeriesDate = data
        ds.ImagePositionPatient = [0.0, 0.0, esp * i]
        ds.ImageOrientationPatient = [1, 0, 0, 0, 1, 0]
        ds.PixelSpacing = [1.0, 1.0]
        ds.SliceThickness = esp
        ds.Rows = ds.Columns = 4
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = ds.BitsStored = 16
        ds.HighBit = 15
        ds.PixelRepresentation = 1
        ds.PixelData = np.zeros((4, 4), np.int16).tobytes()
        ds.save_as(os.path.join(pasta, "%s%03d.dcm" % (prefixo, i)),
                   enforce_file_format=True)


class AppFalso(object):

    def __init__(self):
        self.rotas = {}

    def _reg(self, metodo, caminho):
        def dec(fn):
            self.rotas[(metodo, caminho)] = fn
            return fn
        return dec

    def get(self, caminho, **kw):
        return self._reg(u"GET", caminho)

    def post(self, caminho, **kw):
        return self._reg(u"POST", caminho)


class PedidoFalso(object):
    def __init__(self, corpo):
        self._c = corpo

    async def json(self):
        return self._c


def _post(app, rota, corpo):
    import asyncio
    import json
    r = asyncio.run(app.rotas[(u"POST", rota)](PedidoFalso(corpo)))
    return json.loads(bytes(r.body).decode("utf-8"))


def _get(app, rota, **kw):
    import json
    r = app.rotas[(u"GET", rota)](**kw)
    return json.loads(bytes(r.body).decode("utf-8"))


def _esperar_busca(app, d, teto_s=60.0):
    import time as _time
    fim = _time.time() + teto_s
    while d.get("buscando") and _time.time() < fim:
        _time.sleep(0.05)
        d = _get(app, u"/api/elastic/varredura", v=d.get("v") or u"")
    return d


def teste_a_varredura_e_a_da_suite():
    secao(u"a varredura é a da Suite, pasta a pasta, sem ler nada duas vezes")
    import radai_dicom
    import radai_elastic_screen as T

    tela = sem_docstring(fonte("radai_elastic_screen.py"))
    checar(u"a tela não usa mais a varredura do Rodar agora",
           "radai_batch" not in tela, u"radai_batch no fonte")
    checar(u"e busca pela varredura da Suite (`radai_dicom.buscar_series`)",
           "radai_dicom.buscar_series(" in tela)
    checar(u"o caminho longo é o da Suite, e não uma cópia",
           "def caminho_longo" not in tela
           and "radai_dicom.caminho_longo(" in tela)

    base = _tempfile.mkdtemp(prefix="radai_ac_elastic_")
    U = dict((k, u"9.9.9.222222222.%d" % k) for k in range(1, 8))
    gravar_serie(os.path.join(base, "PAC", "EST", "TC"), U[1], n=12)
    gravar_serie(os.path.join(base, "PAC", "EST", "RM"), U[2], n=9,
                 modalidade="MR")
    gravar_serie(os.path.join(base, "PAC", "EST", "POUCOS"), U[3], n=3)
    gravar_serie(os.path.join(base, "PAC", "EST", "RS"), U[4], n=10,
                 modalidade="RTSTRUCT")
    gravar_serie(os.path.join(base, "PAC", "_RadAI"), U[5], n=10)
    misto = os.path.join(base, "PAC", "MISTO")
    gravar_serie(misto, U[6], n=10)
    gravar_serie(os.path.join(misto, "SUB"), U[7], n=10)
    with open(os.path.join(base, "DICOMDIR"), "wb") as f:
        f.write(b"\0" * 128 + b"DICM" + b"\0" * 64)
    with open(os.path.join(base, "PAC", "estudo.zip"), "wb") as f:
        f.write(b"PK\x05\x06" + b"\0" * 18)
    with open(os.path.join(base, "leiame.txt"), "w") as f:
        f.write(u"texto")

    lidas = []
    original = radai_dicom.varrer_pasta

    def espiao(pasta, *a, **k):
        lidas.append(os.path.normcase(radai_dicom.sem_prefixo(pasta)))
        return original(pasta, *a, **k)

    radai_dicom.varrer_pasta = espiao
    try:
        v = T.nova_varredura(base, False)
        T.varrer_pasta(v)
    finally:
        radai_dicom.varrer_pasta = original
    achadas = dict((a["uid"], a) for a in T.achadas(v))
    checar(u"a TC e a RM da subpasta funda são achadas",
           U[1] in achadas and U[2] in achadas, str(sorted(achadas)))
    checar(u"a série de 3 cortes fica de fora (mínimo de %d)" % T.MIN_CORTES,
           U[3] not in achadas)
    checar(u"a estrutura (RTSTRUCT) não é série de imagem para fundir",
           U[4] not in achadas)
    checar(u"a pasta _RadAI é pulada, como na Suite", U[5] not in achadas)
    checar(u"a pasta com arquivos E subpasta dá as duas séries",
           U[6] in achadas and U[7] in achadas)
    checar(u"cada pasta vai uma vez só à varredura da Suite",
           len(lidas) == len(set(lidas)), str(len(lidas)))
    checar(u"  e a pasta mista e a subpasta dela são lidas, cada uma sozinha",
           os.path.normcase(misto) in lidas
           and os.path.normcase(os.path.join(misto, "SUB")) in lidas)
    checar(u"cada arquivo é lido uma vez (12+9+3+10+10+10 da série, "
           u"o DICOMDIR, o .zip e o texto)",
           v["arquivos"] == 57, str(v["arquivos"]))
    checar(u"a série achada guarda a pasta dos cortes e a data",
           achadas.get(U[1], {}).get("cortes") == 12
           and achadas.get(U[1], {}).get("date") == u"20240115"
           and os.path.basename(achadas.get(U[1], {}).get("pasta", u""))
           == u"TC", str(achadas.get(U[1]))[:140])
    checar(u"e o número e a espessura medidos pela Suite",
           achadas.get(U[1], {}).get("numero") == 3
           and abs(float(achadas.get(U[1], {}).get("espessura_mm") or 0)
                   - 2.5) < 1e-6, str(achadas.get(U[1]))[:140])
    checar(u"o progresso conta pastas e arquivos",
           v["pastas"] >= 8 and v["arquivos"] >= 40,
           u"%d pastas · %d arquivos" % (v["pastas"], v["arquivos"]))
    checar(u"o .zip é contado, e não aberto", v["zips"] == 1, str(v["zips"]))
    av = T.avisos_da_varredura(v)
    checar(u"e o aviso diz que a busca não abre .zip",
           any(u".zip" in a for a in av), u" | ".join(av)[:120])

    vistos = []

    def parar_no_meio():
        vistos.append(1)
        if len(vistos) >= 15:
            v3["parado"] = True

    v3 = T.nova_varredura(base, False)
    radai_dicom.varrer_pasta = (
        lambda pasta, parar=None, ao_ler=None, nomes=None: original(
            pasta, parar, (lambda: (ao_ler and ao_ler(), parar_no_meio())),
            nomes))
    try:
        T.varrer_pasta(v3)
    finally:
        radai_dicom.varrer_pasta = original
    checar(u"a parada vale no meio da pasta, e não só entre pastas",
           v3["parado"] and v3["arquivos"] == 15,
           u"parado=%s · %d arquivos" % (v3["parado"], v3["arquivos"]))

    if os.name == "nt":
        fundo = radai_dicom.caminho_longo(base)
        for k in range(9):
            fundo = os.path.join(fundo, u"subpasta_comprida_%02d_%s" % (k, u"x" * 18))
        checar(u"a pasta funda do fantoma passa de 260 caracteres",
               len(fundo) > 300, str(len(fundo)))
        U8 = u"9.9.9.222222222.8"
        primeira = os.path.join(radai_dicom.caminho_longo(base),
                                u"subpasta_comprida_00_%s" % (u"x" * 18))
        try:
            gravar_serie(fundo, U8, n=8)
            v2 = T.nova_varredura(base, False)
            T.varrer_pasta(v2)
            checar(u"e a série lá no fundo é achada",
                   U8 in [a["uid"] for a in T.achadas(v2)],
                   u"%d achadas" % len(T.achadas(v2)))
        finally:
            import shutil
            shutil.rmtree(primeira, ignore_errors=True)


def teste_as_rotas_de_pasta_executam():
    secao(u"as rotas de pasta EXECUTAM, como trabalho que a tela consulta")
    import json
    import radai_config
    import radai_elastic_screen as T

    app = AppFalso()
    T.montar(app)
    checar(u"`montar` registrou as rotas da busca",
           (u"POST", u"/api/elastic/series") in app.rotas
           and (u"GET", u"/api/elastic/varredura") in app.rotas
           and (u"POST", u"/api/elastic/parar_busca") in app.rotas
           and (u"POST", u"/api/elastic/remover_pasta") in app.rotas,
           str(sorted(c for _m, c in app.rotas)))

    base = _tempfile.mkdtemp(prefix="radai_ac_elastic_")
    A = os.path.join(base, "TC")
    B = os.path.join(base, "RM")
    UA = u"9.9.9.111111111.1001"
    UB = u"9.9.9.111111111.2002"
    gravar_serie(A, UA, n=12)
    gravar_serie(B, UB, n=9, modalidade="MR")

    root_real = radai_config.root_configurado
    radai_config.root_configurado = lambda: u""
    try:
        d = _post(app, u"/api/elastic/series", {"pasta": A})
        checar(u"o pedido volta na hora, com o número da busca",
               bool(d.get("v")) and "buscando" in d, str(d)[:110])
        d = _esperar_busca(app, d)
        checar(u"a busca termina e devolve a série da pasta",
               not d.get("buscando") and len(d.get("series") or []) == 1
               and len(d.get("pastas") or []) == 1, str(d)[:140])
        checar(u"e diz o que olhou",
               d.get("pastas_olhadas", 0) >= 1 and d.get("arquivos", 0) >= 12
               and d.get("series_achadas") == 1,
               u"%s pastas · %s arquivos" % (d.get("pastas_olhadas"),
                                            d.get("arquivos")))

        d = _esperar_busca(app, _post(app, u"/api/elastic/series",
                                      {"pasta": B, "acumular": True}))
        checar(u"a segunda pasta SOMA pela rota", len(d["series"]) == 2,
               u"%d séries" % len(d["series"]))
        checar(u"e as duas pastas voltam na resposta",
               [p["pasta"] for p in d["pastas"]] == [A, B],
               str([p["pasta"] for p in d["pastas"]]))
        checar(u"e o UID não está na resposta da rota",
               UA not in json.dumps(d) and UB not in json.dumps(d))
        checar(u"nem o prefixo de caminho longo",
               u"\\\\?\\" not in u"".join(p["pasta"] for p in d["pastas"]))

        d = _get(app, u"/api/elastic/varredura", v=u"")
        checar(u"reabrir a tela devolve a lista guardada, sem varrer de novo",
               len(d.get("series") or []) == 2 and not d.get("buscando"),
               str(d)[:110])

        d = _esperar_busca(app, _post(app, u"/api/elastic/series",
                                      {"pasta": B}))
        checar(u"«Procurar séries» SUBSTITUI a lista",
               len(d["series"]) == 1 and len(d["pastas"]) == 1,
               u"%d séries · %d pastas" % (len(d["series"]),
                                           len(d["pastas"])))

        d = _esperar_busca(app, _post(
            app, u"/api/elastic/series",
            {"pasta": os.path.join(base, "NAO_EXISTE"), "acumular": True}))
        checar(u"pasta inexistente responde erro", bool(d.get("erro")),
               str(d.get("erro"))[:70])
        checar(u"e a lista ANTERIOR volta junto com o erro",
               len(d.get("series") or []) == 1, str(d)[:110])

        d = _post(app, u"/api/elastic/series", {"pasta": B, "acumular": True})
        checar(u"a pasta repetida é recusada, com o número dela",
               u"já está na lista" in (d.get("erro") or u"")
               and not d.get("v"), str(d.get("erro"))[:80])
        checar(u"e nada foi acrescentado", len(d["series"]) == 1,
               u"%d séries" % len(d["series"]))

        d = _esperar_busca(app, _post(app, u"/api/elastic/series",
                                      {"pasta": A, "acumular": True}))
        checar(u"volta a haver duas pastas", len(d["pastas"]) == 2)
        d = _post(app, u"/api/elastic/remover_pasta", {"n": 1})
        checar(u"tirar a pasta 1 pela rota leva a série dela",
               len(d["series"]) == 1 and len(d["pastas"]) == 1
               and d["pastas"][0]["pasta"] == A,
               str(d["pastas"]))
        checar(u"e a que sobrou é renumerada para [1]",
               d["series"][0]["rotulo"].startswith(u"[1]"),
               d["series"][0]["rotulo"][:22])
        d = _post(app, u"/api/elastic/remover_pasta", {"n": 77})
        checar(u"número que não existe não apaga nada, e diz",
               len(d["series"]) == 1 and len(d.get("avisos") or []) == 1,
               str(d.get("avisos"))[:80])

        d = _post(app, u"/api/elastic/series", {"pasta": u""})
        checar(u"campo vazio sem ROOT configurado diz como resolver",
               u"Procurar" in (d.get("erro") or u"") and not d.get("v"),
               str(d.get("erro"))[:80])
        radai_config.root_configurado = lambda: A
        d = _esperar_busca(app, _post(app, u"/api/elastic/series",
                                      {"pasta": u""}))
        checar(u"campo vazio varre o ROOT configurado",
               len(d["series"]) == 1 and d["pastas"][0]["pasta"] == A,
               str(d["pastas"])[:80])
        d = _get(app, u"/api/elastic/varredura", v=u"inexistente")
        checar(u"busca desconhecida diz que o programa pode ter reiniciado",
               u"reiniciado" in (d.get("erro") or u""), str(d.get("erro")))
    finally:
        radai_config.root_configurado = root_real


def teste_a_busca_mostra_o_que_acha_e_para():
    secao(u"a busca mostra cada série quando acha, e para quando pedem")
    import threading
    import time as _time
    import radai_config
    import radai_elastic_screen as T

    base = _tempfile.mkdtemp(prefix="radai_ac_elastic_")
    U1, U2 = u"9.9.9.333333333.1", u"9.9.9.333333333.2"
    gravar_serie(os.path.join(base, "A"), U1, n=10)
    gravar_serie(os.path.join(base, "B"), U2, n=10)

    app = AppFalso()
    T.montar(app)
    import radai_dicom
    solta = threading.Event()
    lidas = []
    original = radai_dicom.varrer_pasta

    def devagar(pasta, *a, **k):
        if os.path.basename(pasta) in (u"A", u"B"):
            lidas.append(pasta)
        if os.path.basename(pasta) == u"B":
            solta.wait(20.0)
        return original(pasta, *a, **k)

    root_real = radai_config.root_configurado
    radai_config.root_configurado = lambda: u""
    radai_dicom.varrer_pasta = devagar
    try:
        d = _post(app, u"/api/elastic/series", {"pasta": base})
        v = d.get("v")
        fim = _time.time() + 20.0
        while _time.time() < fim:
            d = _get(app, u"/api/elastic/varredura", v=v)
            if len(d.get("series") or []) >= 1 and len(lidas) >= 2:
                break
            _time.sleep(0.05)
        checar(u"com a busca ainda rodando, a primeira série já aparece",
               d.get("buscando") is True and len(d.get("series") or []) == 1,
               u"buscando=%s séries=%d" % (d.get("buscando"),
                                          len(d.get("series") or [])))
        d = _post(app, u"/api/elastic/parar_busca", {"v": v})
        checar(u"«Parar a busca» para na hora, sem esperar a pasta lenta",
               d.get("buscando") is False, str(d.get("buscando")))
        checar(u"e guarda o que já tinha achado",
               len(d.get("series") or []) == 1, str(d)[:110])
        checar(u"e avisa que a lista é parcial",
               any(u"interrompida" in a for a in d.get("avisos") or ()),
               str(d.get("avisos"))[:110])
        solta.set()
        _time.sleep(0.3)
        d = _get(app, u"/api/elastic/varredura", v=v)
        checar(u"o que a busca parada achou depois não entra na lista",
               len(d.get("series") or []) == 1, str(d)[:110])

        lidas[:] = []
        solta.clear()
        d1 = _post(app, u"/api/elastic/series", {"pasta": base})
        fim = _time.time() + 20.0
        while len(lidas) < 2 and _time.time() < fim:
            _time.sleep(0.05)
        radai_dicom.varrer_pasta = original
        d2 = _esperar_busca(app, _post(app, u"/api/elastic/series",
                                       {"pasta": base}))
        solta.set()
        checar(u"uma busca nova toma o lugar da que estava rodando",
               d1.get("v") != d2.get("v") and not d2.get("buscando")
               and len(d2.get("series") or []) == 2,
               u"%d séries" % len(d2.get("series") or []))
        velha = _get(app, u"/api/elastic/varredura", v=d1.get("v"))
        checar(u"e a velha passa a ser desconhecida",
               bool(velha.get("erro")), str(velha.get("erro"))[:60])
    finally:
        solta.set()
        radai_dicom.varrer_pasta = original
        radai_config.root_configurado = root_real


def teste_o_ciclo_roda():
    secao(u"o ciclo roda ponta a ponta")
    import numpy as np
    import SimpleITK as sitk
    import radai_elastic as E

    def bloco(desloca=0.0, raio=6.0):
        nz, ny, nx = 20, 34, 34
        z, y, x = np.mgrid[0:nz, 0:ny, 0:nx].astype(np.float32)
        v = np.full((nz, ny, nx), -1000.0, dtype=np.float32)
        r = np.sqrt(((y - ny / 2.0) / 12.0) ** 2 + ((x - nx / 2.0) / 13.0) ** 2)
        v[r < 1] = 40.0
        v[(r >= 0.88) & (r < 1)] = 300.0
        d = np.sqrt((z - nz / 2.0) ** 2 + (y - ny / 2.0 - desloca) ** 2
                    + (x - nx / 2.0) ** 2)
        v[d < raio] = -20.0
        img = sitk.GetImageFromArray(v)
        img.SetSpacing((3.0, 3.0, 3.0))
        img.SetOrigin((-nx * 1.5, -ny * 1.5, -nz * 1.5))
        return img

    fases = []
    r = E.fundir(bloco(0.0, 5.0), bloco(1.5, 9.0), esp_mm=3.0, malha=5,
                 prog=lambda f, i, v: fases.append(f) if i < 0 else None)
    checar(u"devolve as sete chaves",
           set(r) >= {"fixa", "movel", "movel_rig", "fundida", "campo",
                      "transformada", "laudo"},
           str(sorted(r)))
    checar(u"e a móvel-só-rígida existe (o que a deformação ACRESCENTOU)",
           r["movel_rig"].GetSize() == r["fixa"].GetSize())
    checar(u"o laudo sai JUNTO com a imagem, e não depois",
           bool(r["laudo"].get("veredito")), r["laudo"].get("veredito"))
    checar(u"as fases foram anunciadas em ordem",
           fases[:3] == [u"preparando", u"rígido", u"deformável"],
           u" → ".join(fases))
    checar(u"e todas as fases da barra existem no motor",
           set(n for n, _p in __import__("radai_elastic_screen").PESO)
           <= set(fases) | {u"campo", u"inverso", u"laudo", u"reamostrando"},
           u" · ".join(fases))
    checar(u"a fundida tem a grade da fixa",
           r["fundida"].GetSize() == r["fixa"].GetSize())

    nz = r["fixa"].GetSize()[2]
    g = E.grade_deformada(r["campo"], nz // 2, passo=6)
    checar(u"a grade deformada devolve linhas do corte pedido", len(g) > 4,
           u"%d linhas" % len(g))
    checar(u"e cada linha tem pontos", all(len(l) > 3 for l in g))
    s = E.setas(r["campo"], nz // 2, passo=6)
    checar(u"as setas trazem módulo em mm",
           all(len(a) == 5 for a in s) if s else True, u"%d setas" % len(s))
    x = E.xadrez(r["fixa"], r["fundida"], 8)
    checar(u"o xadrez tem a forma da fixa", x.GetSize() == r["fixa"].GetSize())


def _fisico(ref):
    import numpy as np
    nx, ny, nz = ref.GetSize()
    k, j, i = np.mgrid[0:nz, 0:ny, 0:nx].astype(np.float64)
    d = np.array(ref.GetDirection()).reshape(3, 3)
    s = np.array(ref.GetSpacing())
    o = np.array(ref.GetOrigin())
    idx = np.stack([i * s[0], j * s[1], k * s[2]], axis=-1)
    return o + idx @ d.T


def _campo_fisico(ref, fn):
    import SimpleITK as sitk
    import numpy as np
    p = _fisico(ref)
    d = fn(p[..., 0], p[..., 1], p[..., 2])
    c = sitk.GetImageFromArray(np.ascontiguousarray(d, dtype=np.float64),
                               isVector=True)
    c.CopyInformation(ref)
    return c


SAGITAL = (0.0, 0.0, -1.0, 1.0, 0.0, 0.0, 0.0, -1.0, 0.0)


def _cabeca_rm(nz=20, ny=48, nx=48, sinal=600.0, ruido=12.0, semente=7):
    import numpy as np
    import SimpleITK as sitk
    rng = np.random.RandomState(semente)
    v = np.abs(rng.normal(0.0, ruido, (nz, ny, nx))).astype(np.float32)
    y, x = np.mgrid[0:ny, 0:nx].astype(np.float32)
    r = np.sqrt((y - ny / 2.0) ** 2 + (x - nx / 2.0) ** 2)
    cort = np.zeros((ny, nx), dtype=np.float32)
    cort[r < 20] = sinal
    cort[(r >= 17) & (r < 19)] = 25.0
    cort[r < 17] = 0.66 * sinal
    cort[(np.abs(y - ny / 2.0) < 3) & (np.abs(x - nx / 2.0) < 3)] = 60.0
    v[:] = np.maximum(v, cort[None])
    img = sitk.GetImageFromArray(v)
    img.SetSpacing((2.0, 2.0, 2.0))
    return img


def teste_a_rm_nao_e_tc():
    secao(u"RM não é TC: fundo, corpo e janela perguntados à imagem")
    import numpy as np
    import SimpleITK as sitk
    import radai_elastic as E

    rm = _cabeca_rm()
    tc_arr = np.full((12, 30, 30), -1000.0, dtype=np.float32)
    tc_arr[2:10, 8:22, 8:22] = 40.0
    tc = sitk.GetImageFromArray(tc_arr)
    checar(u"a TC é reconhecida como HU (há ar abaixo de −500)",
           E.eh_hu(tc) is True)
    checar(u"e a RM não é", E.eh_hu(rm) is False)
    checar(u"e a pergunta vale para o array também",
           E.eh_hu(sitk.GetArrayViewFromImage(rm)) is False)

    checar(u"o fundo da TC continua −1024", E.fundo_de(tc) == -1024.0)
    minimo = float(sitk.GetArrayViewFromImage(rm).min())
    checar(u"e o da RM é o mínimo do sinal, e não −1024",
           E.fundo_de(rm) == minimo, u"%.2f" % E.fundo_de(rm))
    p = E.preparar(rm, 3.0)
    checar(u"a RM preparada não ganha valor impossível na borda",
           float(sitk.GetArrayViewFromImage(p).min()) >= minimo - 1e-3,
           u"mínimo %.1f" % float(sitk.GetArrayViewFromImage(p).min()))

    m = E.mascara_corpo(rm)
    parte = float(m.sum()) / m.size
    area = np.pi * 20.0 ** 2 / (48 * 48)
    checar(u"a máscara do corpo da RM é a cabeça, e não a grade inteira",
           abs(parte - area) < 0.06, u"%.1f%% da grade, a cabeça tem %.1f%%"
           % (100 * parte, 100 * area))
    velho = E.mascara_corpo(rm, limiar=-300.0)
    checar(u"ISCA: com o limiar antigo a máscara da RM era a grade inteira",
           float(velho.sum()) / velho.size > 0.99,
           u"%.1f%%" % (100.0 * velho.sum() / velho.size))
    meio = m[:, 24, 24]
    checar(u"o líquido escuro no meio do encéfalo fica DENTRO do corpo",
           bool(meio.all()))
    checar(u"e o couro, do outro lado do osso escuro, também",
           bool(m[:, 24, 24 + 19].all()))
    checar(u"inclusive nos cortes da borda, onde o tubo é aberto",
           bool(m[0].sum() > 0.8 * m[10].sum())
           and bool(m[-1].sum() > 0.8 * m[10].sum()),
           u"%d · %d · %d" % (m[0].sum(), m[10].sum(), m[-1].sum()))

    checar(u"a janela da TC continua 40/400",
           E.janela_de(tc) == (40.0, 400.0))
    c, w = E.janela_de(rm, m)
    checar(u"e a da RM sai do sinal dela (não 40/400)",
           (c, w) != (40.0, 400.0) and 200.0 < c + w / 2.0 < 700.0,
           u"centro %.0f largura %.0f" % (c, w))


def teste_o_jacobiano_olha_a_direcao():
    secao(u"o jacobiano com direção sagital e oblíqua")
    import math
    import numpy as np
    import SimpleITK as sitk
    import radai_elastic as E

    a = math.radians(25.0)
    obliqua = (math.cos(a), -math.sin(a), 0.0, math.sin(a), math.cos(a), 0.0,
               0.0, 0.0, 1.0)
    casos = (
        (u"expande 1,2× em x", lambda X, Y, Z: np.stack(
            [0.2 * X, 0 * X, 0 * X], -1), 1.2),
        (u"comprime 0,7× em z", lambda X, Y, Z: np.stack(
            [0 * X, 0 * X, -0.3 * Z], -1), 0.7),
        (u"cisalha x por y (preserva volume)", lambda X, Y, Z: np.stack(
            [0.5 * Y, 0 * X, 0 * X], -1), 1.0),
    )
    for nome_d, direcao in ((u"sagital", SAGITAL), (u"oblíqua", obliqua)):
        ref = grade(nz=20, ny=24, nx=28, direcao=direcao)
        for rot, fn, esperado in casos:
            c = _campo_fisico(ref, fn)
            j = sitk.GetArrayFromImage(E.jacobiano(c))[2:-2, 2:-2, 2:-2]
            checar(u"%s, %s: jacobiano %.3f" % (nome_d, rot, esperado),
                   abs(float(np.median(j)) - esperado) < 1e-3,
                   u"mediana %.4f" % float(np.median(j)))
    ref = grade(nz=20, ny=24, nx=28, direcao=SAGITAL)
    c = _campo_fisico(ref, casos[0][1])
    cru = sitk.GetArrayFromImage(
        sitk.DisplacementFieldJacobianDeterminant(c))[2:-2, 2:-2, 2:-2]
    checar(u"ISCA: o filtro cru do ITK dá o número ERRADO na sagital",
           abs(float(np.median(cru)) - 1.2) > 0.1,
           u"mediana crua %.4f" % float(np.median(cru)))

    ang = math.radians(8.0)
    rot = np.array([[math.cos(ang), -math.sin(ang), 0.0],
                    [math.sin(ang), math.cos(ang), 0.0], [0.0, 0.0, 1.0]])

    def rigido(X, Y, Z):
        p = np.stack([X, Y, Z], -1)
        return (p @ rot.T) - p + np.array([3.0, -2.0, 5.0])

    c = _campo_fisico(ref, rigido)
    j = sitk.GetArrayFromImage(E.jacobiano(c))[2:-2, 2:-2, 2:-2]
    checar(u"um rígido puro numa grade sagital tem jacobiano 1,000",
           abs(float(j.min()) - 1.0) < 1e-6 and abs(float(j.max()) - 1.0)
           < 1e-6, u"%.6f..%.6f" % (float(j.min()), float(j.max())))
    checar(u"e o jacobiano volta com a geometria do campo",
           E.jacobiano(c).GetDirection() == c.GetDirection()
           and E.jacobiano(c).GetOrigin() == c.GetOrigin())


def teste_o_veredito_nao_inventa_compressao():
    secao(u"o texto do veredito com jacobiano negativo")
    import radai_elastic as E
    r = {"dobras": 12, "dobras_parte": 0.3, "jac_min": -0.363,
         "jac_max": 1.5, "consist_p95": 1.0, "desloc_max": 10.0,
         "cobertura_parte": None}
    v, porques = E._veredito(r)
    texto = u" ".join(porques)
    checar(u"o veredito é REPROVA", v == "reprova", v)
    checar(u"e nenhum porquê fala em «1000000»", u"1000000" not in texto,
           texto[:120])
    checar(u"o mínimo negativo é dito como jacobiano, sem fator inventado",
           u"-0.363" in texto and u"Compressão de até" not in texto,
           texto[:160])
    checar(u"ISCA: a conta antiga dava um milhão de vezes",
           u"%.2f" % (1.0 / max(1e-6, r["jac_min"])) == u"1000000.00")
    r2 = dict(r, dobras=0, dobras_parte=0.0, jac_min=0.145)
    v2, p2 = E._veredito(r2)
    checar(u"e com mínimo POSITIVO a compressão continua dita com o fator",
           v2 == "atencao" and any(u"6.90x" in p for p in p2), u" ".join(p2))


def teste_a_partida_do_rigido():
    secao(u"de onde o rígido parte")
    import numpy as np
    import SimpleITK as sitk
    import radai_elastic as E

    def volume(origem_z, nz, origem_x=0.0):
        esp = 2.0
        zz = origem_z + esp * np.arange(nz)
        y, x = np.mgrid[0:40, 0:40].astype(np.float32)
        v = np.zeros((nz, 40, 40), dtype=np.float32)
        for k, z in enumerate(zz):
            r = np.sqrt(((y - 20) / 14.0) ** 2 + ((x - 20) / 11.0) ** 2)
            v[k][r < 1] = 300.0 + 2.0 * z
            v[k][(y > 24) & (y < 30) & (x > 22) & (x < 28)] = 900.0
        img = sitk.GetImageFromArray(v)
        img.SetSpacing((esp, esp, esp))
        img.SetOrigin((origem_x, 0.0, origem_z))
        return img

    fixa = volume(0.0, 60)
    movel = volume(80.0, 20)
    tx, nome, valores = E.inicio_do_rigido(fixa, movel)
    checar(u"mesma sessão, campo menor: parte das COORDENADAS",
           nome == "coordenadas", u"%s %s" % (nome, valores))
    geo = sitk.CenteredTransformInitializer(
        fixa, movel, sitk.Euler3DTransform(),
        sitk.CenteredTransformInitializerFilter.GEOMETRY)
    desloc = float(np.linalg.norm(geo.GetTranslation()))
    checar(u"ISCA: partir dos centros começava %.0f mm fora do lugar" % desloc,
           desloc > 30.0, u"%.1f mm" % desloc)
    checar(u"e a partida escolhida começa no lugar certo",
           float(np.linalg.norm(tx.GetTranslation())) < 1e-6)

    longe = volume(80.0, 20, origem_x=900.0)
    _tx, nome2, valores2 = E.inicio_do_rigido(fixa, longe)
    checar(u"sessões sem relação de coordenadas: parte dos CENTROS",
           nome2 == "centros", u"%s %s" % (nome2, valores2))
    checar(u"e a partida que nem se calcula não conta",
           valores2.get("coordenadas") is None, str(valores2))


def teste_a_cobertura():
    secao(u"a cobertura: onde a móvel tem imagem")
    import numpy as np
    import SimpleITK as sitk
    import radai_elastic as E

    fixa = sitk.GetImageFromArray(np.full((30, 20, 20), 100.0, np.float32))
    fixa.SetSpacing((2.0, 2.0, 2.0))
    parcial = sitk.GetImageFromArray(np.full((9, 20, 20), 100.0, np.float32))
    parcial.SetSpacing((2.0, 2.0, 2.0))
    ident = sitk.Euler3DTransform()
    s = E.suporte(parcial, ident, fixa)
    checar(u"o suporte é a faixa em que a móvel existe",
           s.shape == (30, 20, 20) and bool(s[:9].all())
           and not bool(s[10:].any()), u"%d cortes" % int(s.any(axis=(1, 2))
                                                         .sum()))
    c = campo_de(fixa, lambda z, y, x: np.zeros(z.shape + (3,)))
    l = E.laudo(c, None, dentro=s, cobertura=float(s.sum()) / s.size)
    checar(u"o laudo diz a cobertura em %", abs(l["cobertura_parte"] - 30.0)
           < 0.01, u"%.2f" % l["cobertura_parte"])
    checar(u"abaixo do mínimo ela chama a atenção, mesmo sem dobra",
           l["veredito"] == "atencao"
           and any(u"cobre só" in p for p in l["porques"]),
           u"%s · %s" % (l["veredito"], l["porques"][0][:70]))
    cheio = E.laudo(c, None, dentro=np.ones((30, 20, 20), bool),
                    cobertura=1.0)
    checar(u"com a móvel cobrindo tudo, o mesmo campo passa",
           cheio["veredito"] == "passa", cheio["veredito"])
    checar(u"e sem medida de cobertura o laudo não inventa uma",
           E.laudo(c, None)["cobertura_parte"] is None)
    checar(u"o limiar é declarado como nosso, ao lado dos outros",
           E.COBERTURA_MIN_PARTE == 50.0)


def teste_a_serie_certa_da_pasta():
    secao(u"a fusão abre a série escolhida, e não a primeira da pasta")
    import radai_elastic_screen as T
    lidas = []

    def ler(pasta, uid=None):
        lidas.append((pasta, uid))
        return u"volume de %s" % (uid or u"PRIMEIRA-DA-PASTA")

    pasta = _tempfile.mkdtemp(prefix="radai_ac_elastic_")
    s = {"b": u"x", "uid": u"9.9.9.2", "pasta": pasta, "curto": u"9.9.9.2"}
    v = T.carregar_serie(s, ler=ler)
    checar(u"o UID da série vai para o leitor", lidas[-1][1] == u"9.9.9.2",
           str(lidas[-1]))
    checar(u"e o volume é o da série pedida", v == u"volume de 9.9.9.2", v)
    checar(u"e a leitura é a da pasta guardada", lidas[-1][0] == pasta)
    try:
        T.carregar_serie(dict(s, pasta=os.path.join(pasta, u"SUMIU")),
                         ler=ler)
        checar(u"pasta que sumiu levanta com o motivo", False)
    except ValueError as e:
        checar(u"pasta que sumiu levanta com o motivo",
               u"sumiu" in str(e), str(e)[:80])
    checar(u"ISCA: sem o UID o leitor devolveria a primeira da pasta",
           ler(s["pasta"]) == u"volume de PRIMEIRA-DA-PASTA")
    checar(u"a leitura não passa mais pelo .zip do Rodar agora",
           "resolver_pasta" not in sem_docstring(
               fonte("radai_elastic_screen.py")))
    g = T._serie_guardada({"uid": u"9.9.9.3", "pasta": u"C:\\P\\CT",
                           "cortes": 30}, lambda p, u: u"bilhete")
    tela = T.para_a_tela([{"pasta": u"C:\\P", "series": [g]}])
    checar(u"a série guardada tem a pasta para a fusão",
           g["pasta"] == u"C:\\P\\CT")
    checar(u"e ela não chega à tela",
           u"C:\\\\P\\\\CT" not in repr(tela["series"]),
           repr(tela["series"])[:90])


def teste_a_tela_da_rm():
    secao(u"a tela de uma fusão de RM")
    import struct
    import zlib
    import numpy as np
    import radai_elastic_screen as T

    tc = {"hu": (True, True), "janelas": {"fixa": (1, 2), "movel": (3, 4)}}
    for v in T.VISTAS:
        checar(u"entre duas TC a vista «%s» usa a tabela em HU" % v,
               T.janela_da_vista(tc, v) == (T.JANELAS[v], False))
    rm = {"hu": (False, False),
          "janelas": {"fixa": (300.0, 500.0), "movel": (900.0, 1600.0)}}
    checar(u"na RM a fixa usa a janela DELA",
           T.janela_da_vista(rm, "fixa") == ((300.0, 500.0), False))
    checar(u"e a fundida, a da móvel",
           T.janela_da_vista(rm, "fundida") == ((900.0, 1600.0), False))
    checar(u"e o xadrez sai normalizado (cada série pela sua janela)",
           T.janela_da_vista(rm, "xadrez") == ((0.5, 1.0), True))
    n = T._normalizada(np.array([50.0, 300.0, 550.0, 900.0]), (300.0, 500.0))
    checar(u"a normalização leva a janela a 0..1",
           np.allclose(n, [0.0, 0.5, 1.0, 1.0]), str(n))

    fundo = np.full((2, 3), 0.5)
    j = np.array([[1.0, 0.5, 2.0], [0.0, -0.4, 1.0]])
    rgb = T.jacobiano_em_cor(j, fundo)
    checar(u"sai RGB do tamanho do corte", rgb.shape == (2, 3, 3)
           and rgb.dtype == np.uint8, str(rgb.shape))
    cinza = int(round(0.5 * 255))
    checar(u"volume preservado (1,0) é só a anatomia",
           tuple(rgb[0, 0]) == (cinza, cinza, cinza), str(tuple(rgb[0, 0])))
    checar(u"compressão (0,5) puxa para o AZUL",
           rgb[0, 1, 2] > rgb[0, 1, 0], str(tuple(rgb[0, 1])))
    checar(u"expansão (2,0) puxa para o LARANJA",
           rgb[0, 2, 0] > rgb[0, 2, 2], str(tuple(rgb[0, 2])))
    checar(u"0,5× e 2× pintam com a mesma força, cada um do seu lado",
           abs(int(rgb[0, 1, 2]) - cinza - (int(rgb[0, 2, 0]) - cinza)) <= 2)
    checar(u"DOBRA (≤ 0) é vermelho puro, sem mistura",
           tuple(rgb[1, 0]) == T.COR_DOBRA and tuple(rgb[1, 1]) == T.COR_DOBRA,
           str((tuple(rgb[1, 0]), tuple(rgb[1, 1]))))

    png = T.png_rgb(rgb)
    checar(u"é um PNG", png[:8] == b"\x89PNG\r\n\x1a\n")
    larg, alt, prof, tipo = struct.unpack(">IIBB", png[16:26])
    checar(u"RGB de 8 bits, com a largura e a altura do corte",
           (larg, alt, prof, tipo) == (3, 2, 8, 2), str((larg, alt, prof, tipo)))
    i = png.index(b"IDAT")
    tam = struct.unpack(">I", png[i - 4:i])[0]
    cru = zlib.decompress(png[i + 4:i + 4 + tam])
    checar(u"e os bytes são os do corte, linha a linha",
           cru == b"".join(b"\x00" + rgb[y].tobytes() for y in range(2)))

    t = T.tempos_das_fases([(u"preparando", 0.0), (u"rígido", 1.0),
                            (u"deformável", 3.5)], 10.0)
    checar(u"o tempo de cada fase vai do anúncio dela ao da seguinte",
           t == [(u"preparando", 1.0), (u"rígido", 2.5),
                 (u"deformável", 6.5)], str(t))


def _bloco_ct(desloca=0.0, raio=6.0, sinal=None):
    import numpy as np
    import SimpleITK as sitk
    nz, ny, nx = 20, 34, 34
    z, y, x = np.mgrid[0:nz, 0:ny, 0:nx].astype(np.float32)
    v = np.full((nz, ny, nx), -1000.0, dtype=np.float32)
    r = np.sqrt(((y - ny / 2.0) / 12.0) ** 2 + ((x - nx / 2.0) / 13.0) ** 2)
    v[r < 1] = 40.0
    v[(r >= 0.88) & (r < 1)] = 300.0
    d = np.sqrt((z - nz / 2.0) ** 2 + (y - ny / 2.0 - desloca) ** 2
                + (x - nx / 2.0) ** 2)
    v[d < raio] = -20.0
    if sinal is not None:
        v = (v + 1000.0) / 1300.0 * float(sinal)
    img = sitk.GetImageFromArray(v)
    img.SetSpacing((3.0, 3.0, 3.0))
    img.SetOrigin((-nx * 1.5, -ny * 1.5, -nz * 1.5))
    return img


def teste_o_ciclo_de_rm():
    secao(u"o ciclo numa RM (sem ar negativo)")
    import radai_elastic as E
    f, m = _bloco_ct(0.0, 5.0, sinal=800.0), _bloco_ct(1.5, 8.0, sinal=800.0)
    r = E.fundir(f, m, esp_mm=3.0, malha=5)
    tam = r["fixa"].GetSize()
    grade = tam[0] * tam[1] * tam[2]
    l = r["laudo"]
    checar(u"as duas séries são reconhecidas como NÃO-HU",
           tuple(r["hu"]) == (False, False), str(r["hu"]))
    checar(u"o laudo mede o corpo, e não a grade inteira",
           0 < l["n_voxels"] < 0.8 * grade,
           u"%d de %d" % (l["n_voxels"], grade))
    checar(u"a janela de cada série sai do sinal dela",
           r["janelas"]["fixa"] != (40.0, 400.0)
           and r["janelas"]["movel"] != (40.0, 400.0), str(r["janelas"]))
    checar(u"a cobertura é medida (a móvel cobre o corpo inteiro aqui)",
           l.get("cobertura_parte") is not None
           and l["cobertura_parte"] > 90.0, str(l.get("cobertura_parte")))
    checar(u"e a partida do rígido é dita no laudo",
           l.get("inicio_rigido") in E.INICIOS, str(l.get("inicio_rigido")))
    checar(u"o jacobiano volta pronto para a tela (não recalculado)",
           r.get("jac") is not None
           and r["jac"].GetSize() == r["fixa"].GetSize())


def teste_a_rota_da_fusao_executa():
    secao(u"a rota da fusão EXECUTA, do botão ao PNG")
    import json
    import time as _time
    import radai_config
    import radai_elastic_screen as T

    def post(rota, corpo):
        return _post(app, rota, corpo)

    app = AppFalso()
    T.montar(app)
    base = _tempfile.mkdtemp(prefix="radai_ac_elastic_")
    UF, UM = u"9.9.9.111111111.4004", u"9.9.9.111111111.5005"
    gravar_serie(base, UF, n=20, numero=3, esp=3.0, prefixo="F")
    gravar_serie(base, UM, n=20, numero=4, esp=3.0, prefixo="M")
    volumes = {UF: _bloco_ct(0.0, 5.0, sinal=800.0),
               UM: _bloco_ct(1.5, 8.0, sinal=800.0)}
    pedidas = []

    def carregar_falso(s, ler=None):
        pedidas.append(s.get("uid"))
        return volumes[s.get("uid")]

    root_real = radai_config.root_configurado
    carregar_real = T.carregar_serie
    radai_config.root_configurado = lambda: u""
    T.carregar_serie = carregar_falso
    try:
        d = _esperar_busca(app, post(u"/api/elastic/series", {"pasta": base}))
        bs = [s["b"] for s in d.get("series") or ()]
        checar(u"a lista traz as duas séries", len(bs) == 2, str(d)[:90])
        j = post(u"/api/elastic/fundir", {"fixa": bs[0], "movel": bs[1],
                                         "esp": 3, "malha": 5})
        checar(u"o botão Fundir devolve uma tarefa", bool(j.get("j")), str(j))
        estado = app.rotas[(u"GET", u"/api/elastic/estado")]
        e = {}
        for _ in range(600):
            e = json.loads(bytes(estado(j=j["j"]).body).decode("utf-8"))
            if e.get("pronto") or e.get("erro"):
                break
            _time.sleep(0.05)
        checar(u"a tarefa termina PRONTA, sem erro", bool(e.get("pronto"))
               and not e.get("erro"), str(e.get("erro"))[:120])
        checar(u"a fixa e a móvel são as duas séries ESCOLHIDAS",
               pedidas == [UF, UM], str(pedidas))
        checar(u"o estado traz o laudo com o veredito",
               (e.get("laudo") or {}).get("veredito") in (u"passa",
                                                          u"atencao",
                                                          u"reprova"))
        checar(u"e a proporção da grade, para o palco",
               e.get("nx") and e.get("ny") and e.get("nz"),
               u"%s × %s × %s" % (e.get("nx"), e.get("ny"), e.get("nz")))
        fases = [p[0] for p in e.get("tempos") or ()]
        checar(u"e o tempo de cada fase do ciclo",
               fases[:3] == [u"preparando", u"rígido", u"deformável"]
               and u"inverso" in fases and u"laudo" in fases, str(fases))
        checar(u"e a partida do rígido e a natureza da imagem",
               e.get("inicio") in (u"coordenadas", u"centros")
               and e.get("hu") == [False, False],
               u"%s · %s" % (e.get("inicio"), e.get("hu")))

        corte = app.rotas[(u"GET", u"/api/elastic/corte")]
        for v in T.VISTAS:
            r = corte(j=j["j"], z=e.get("nz", 2) // 2, vista=v)
            ok = (getattr(r, "status_code", 200) == 200
                  and bytes(r.body)[:8] == b"\x89PNG\r\n\x1a\n")
            tipo = bytes(r.body)[25] if ok else None
            quer = 2 if v in T.VISTAS_EM_COR else 0
            checar(u"a vista «%s» sai PNG %s" % (
                v, u"em cor" if quer == 2 else u"em cinza"),
                ok and tipo == quer, u"status %s tipo %s"
                % (getattr(r, "status_code", "?"), tipo))
        sobre = app.rotas[(u"GET", u"/api/elastic/sobre")]
        o = json.loads(bytes(sobre(j=j["j"], z=e.get("nz", 2) // 2, grade=1,
                                   setas=1, dobras=1).body).decode("utf-8"))
        checar(u"a camada SVG responde com grade e marcas de dobra",
               not o.get("erro") and len(o.get("grade") or []) > 2
               and "dobras" in o, str(o.get("erro"))[:80])

        t_viva = e
        tarefa = None
        for cel in (getattr(corte, "__closure__", None) or ()):
            try:
                val = cel.cell_contents
            except ValueError:
                continue
            if callable(val) and getattr(val, "__name__", "") == "_tarefa":
                tarefa = val(j["j"])
        if tarefa is not None:
            guardado = tarefa["r"]["laudo"]
            tarefa["r"]["laudo"] = None
            r = corte(j=j["j"], z=0, vista="fundida")
            checar(u"sem o laudo, a fundida é RECUSADA com 409",
                   getattr(r, "status_code", 0) == 409,
                   str(getattr(r, "status_code", "?")))
            tarefa["r"]["laudo"] = guardado
        else:
            checar(u"achei a tarefa viva para tirar o laudo dela", False,
                   str(t_viva)[:60])
    finally:
        radai_config.root_configurado = root_real
        T.carregar_serie = carregar_real


def _dois_alvos(desloca_b):
    import numpy as np
    import SimpleITK as sitk
    nz, ny, nx = 16, 30, 48
    z, y, x = np.mgrid[0:nz, 0:ny, 0:nx].astype(np.float32)
    v = np.full((nz, ny, nx), 20.0, np.float32)
    v[:, 3:27, 3:45] = 300.0
    v[np.sqrt((z - 8) ** 2 + (y - 15) ** 2 + (x - 13) ** 2) < 5] = 800.0
    v[np.sqrt((z - 8) ** 2 + (y - 15 - desloca_b) ** 2
              + (x - 35) ** 2) < 5] = 800.0
    img = sitk.GetImageFromArray(v)
    img.SetSpacing((2.0, 2.0, 2.0))
    return img


def teste_a_metrica_olha_o_corpo():
    secao(u"a métrica do deformável olha o corpo, e não o ar")
    import numpy as np
    import SimpleITK as sitk
    import radai_elastic as E

    f, m = _dois_alvos(0.0), _dois_alvos(3.0)
    ident = sitk.Euler3DTransform()
    mk = np.zeros((16, 30, 48), bool)
    mk[:, :, :24] = True
    em_b = (slice(4, 12), slice(10, 20), slice(30, 40))
    sem = E.magnitude(E.campo_de(E.compor(ident, E.registrar_deformavel(
        f, m, ident, malha=5)), f))[em_b]
    com = E.magnitude(E.campo_de(E.compor(ident, E.registrar_deformavel(
        f, m, ident, malha=5, mascara=mk)), f))[em_b]
    checar(u"ISCA: sem máscara, o deformável persegue B (fora da região)",
           float(sem.max()) > 0.8, u"máx %.2f mm" % float(sem.max()))
    checar(u"com a máscara, B fica parado: não há amostra lá",
           float(com.max()) < 0.2, u"máx %.2f mm" % float(com.max()))

    fixa = sitk.GetImageFromArray(np.zeros((30, 24, 24), np.float32))
    fixa.SetSpacing((2.0, 2.0, 2.0))
    a = sitk.GetArrayFromImage(fixa)
    a[:, 4:20, 4:20] = 500.0
    fixa = sitk.GetImageFromArray(a)
    fixa.SetSpacing((2.0, 2.0, 2.0))
    parcial = sitk.GetImageFromArray(a[:12].copy())
    parcial.SetSpacing((2.0, 2.0, 2.0))
    guardado = E.MASCARA_MIN_VOXELS
    try:
        E.MASCARA_MIN_VOXELS = 100
        mm = E.mascara_da_metrica(fixa, parcial, sitk.Euler3DTransform())
        corpo = E.mascara_corpo(fixa)
        checar(u"a máscara da métrica existe e tem a forma da grade",
               mm is not None and mm.shape == (30, 24, 24),
               str(None if mm is None else mm.shape))
        checar(u"ela fica DENTRO do corpo (o ar não é sorteado)",
               mm is not None and not bool((mm & ~corpo).any()))
        checar(u"e fora da fatia que a móvel cobre ela é vazia",
               mm is not None and not bool(mm[13:].any())
               and bool(mm[:11].any()),
               u"cortes %d" % (0 if mm is None
                              else int(mm.any(axis=(1, 2)).sum())))
        E.MASCARA_MIN_VOXELS = 10 ** 9
        checar(u"pequena demais para o sorteio: sem máscara, como antes",
               E.mascara_da_metrica(fixa, parcial,
                                    sitk.Euler3DTransform()) is None)
    finally:
        E.MASCARA_MIN_VOXELS = guardado

    visto = {}
    original = E.registrar_deformavel

    def espiao(*a, **k):
        visto["mascara"] = k.get("mascara", "AUSENTE")
        return original(*a, **k)
    try:
        E.MASCARA_MIN_VOXELS = 100
        E.registrar_deformavel = espiao
        r = E.fundir(_bloco_ct(0.0, 5.0, sinal=800.0),
                     _bloco_ct(1.5, 8.0, sinal=800.0), esp_mm=3.0, malha=5)
    finally:
        E.registrar_deformavel = original
        E.MASCARA_MIN_VOXELS = guardado
    mv = visto.get("mascara")
    ok_forma = (mv is not None and not isinstance(mv, str)
                and np.shape(mv) == sitk.GetArrayViewFromImage(
                    r["fixa"]).shape)
    checar(u"a fusão entrega uma máscara ao deformável (ISCA: a versão "
           u"anterior não entregava nenhuma)", ok_forma,
           str(mv if isinstance(mv, str) or mv is None
               else np.shape(mv)))
    checar(u"e ela é o corpo da fixa, não a grade",
           ok_forma and not bool((np.asarray(mv)
                                  & ~E.mascara_corpo(r["fixa"])).any())
           and int(np.asarray(mv).sum()) < np.asarray(mv).size)
    checar(u"o laudo diz onde a métrica olhou",
           r["laudo"].get("metrica_no_corpo") is True,
           str(r["laudo"].get("metrica_no_corpo")))
    so = E.fundir(_bloco_ct(0.0, 5.0, sinal=800.0),
                  _bloco_ct(1.5, 8.0, sinal=800.0), esp_mm=3.0,
                  so_rigido=True)
    checar(u"na fusão só rígida não há métrica de deformável para dizer",
           so["laudo"].get("metrica_no_corpo") is False
           and so["laudo"].get("malha") is None,
           u"%s %s" % (so["laudo"].get("metrica_no_corpo"),
                       so["laudo"].get("malha")))

    import radai_elastic_screen as ES
    js = sem_docstring(fonte("radai_elastic_screen.py"))
    checar(u"a tabela do laudo tem a linha «métrica do deformável»",
           u"m&eacute;trica do deform&aacute;vel" in ES.JS
           and "metrica_no_corpo" in js)


def teste_a_dobra_diz_o_que_tentar():
    secao(u"a dobra diz o que tentar")
    import radai_elastic as E
    import radai_elastic_screen as ES
    base = {"dobras": 120, "dobras_parte": 0.4, "jac_min": -0.2,
            "jac_max": 1.5, "consist_p95": 0.5, "desloc_max": 10.0,
            "cobertura_parte": 90.0}

    def dica(malha):
        v, ps = E._veredito(dict(base, malha=malha))
        return v, any((u"malha %d" % E.MALHA_MENOS_LIVRE) in p for p in ps)
    v8, d8 = dica(8)
    checar(u"com a malha 8 e dobra: reprova, e sugere a malha %d"
           % E.MALHA_MENOS_LIVRE, v8 == "reprova" and d8, u"%s %s" % (v8, d8))
    _v, ps8 = E._veredito(dict(base, malha=8))
    checar(u"e a sugestão vem POR ÚLTIMO, depois dos motivos",
           len(ps8) >= 3 and (u"malha %d" % E.MALHA_MENOS_LIVRE) in ps8[-1],
           ps8[-1][:60])
    checar(u"com a malha %d já em uso, não sugere a mesma"
           % E.MALHA_MENOS_LIVRE, not dica(E.MALHA_MENOS_LIVRE)[1])
    checar(u"na fusão só rígida (sem malha), não sugere malha",
           not dica(None)[1])
    v, ps = E._veredito(dict(base, dobras=0, dobras_parte=0.0, jac_min=0.8,
                             malha=12))
    checar(u"sem dobra, nenhuma sugestão de malha",
           not any(u"malha" in p for p in ps), v)
    checar(u"a tela oferece a malha %d no seletor" % E.MALHA_MENOS_LIVRE,
           (u'<option value="%d">' % E.MALHA_MENOS_LIVRE) in ES.PAGINA)
    checar(u"e o laudo leva a malha usada para a tela",
           E.laudo(campo_de(grade(), lambda z, y, x: __import__("numpy")
                            .zeros(z.shape + (3,))), None,
                   malha=8).get("malha") == 8)


def teste_o_mapa_e_o_numero_sao_da_mesma_regiao():
    secao(u"o mapa e as marcas de dobra falam da região do laudo")
    import numpy as np
    import radai_elastic_screen as ES
    j = np.full((10, 10), 2.0)
    j[:, 1] = -0.5
    j[:, 8] = -0.5
    fundo = np.full((10, 10), 0.4)
    onde = np.zeros((10, 10), bool)
    onde[:, :5] = True
    cinza = int(round(0.4 * 255))
    rgb = ES.jacobiano_em_cor(j, fundo, onde=onde)
    checar(u"fora da região, só a anatomia (sem cor, sem dobra)",
           bool((rgb[:, 5:] == cinza).all()),
           str(rgb[0, 8].tolist()))
    checar(u"dentro, a dobra é vermelho puro e a expansão tem cor",
           tuple(rgb[0, 1]) == ES.COR_DOBRA
           and tuple(rgb[0, 3]) != (cinza, cinza, cinza),
           u"%s %s" % (rgb[0, 1].tolist(), rgb[0, 3].tolist()))
    isca = ES.jacobiano_em_cor(j, fundo)
    checar(u"ISCA: sem a região, o ar ganhava cor e dobra",
           tuple(isca[0, 8]) == ES.COR_DOBRA)
    ys, xs = ES.pontos_de_dobra(j, onde)
    checar(u"as marcas de dobra são só as de dentro (as que o laudo conta)",
           set(xs.tolist()) == {1} and len(ys) == 10,
           u"colunas %s" % sorted(set(xs.tolist())))
    ys2, xs2 = ES.pontos_de_dobra(j, None)
    checar(u"ISCA: sem a região, marcava também as de fora",
           set(xs2.tolist()) == {1, 8})
    vol = np.zeros((3, 10, 10), bool)
    vol[1] = onde
    checar(u"a região do corte sai do resultado da fusão (`dentro`)",
           ES.regiao_do_corte({"dentro": vol}, 1) is not None
           and bool((ES.regiao_do_corte({"dentro": vol}, 1) == onde).all())
           and ES.regiao_do_corte({}, 1) is None
           and ES.regiao_do_corte({"dentro": vol}, 7) is None)
    import radai_elastic as E
    r = E.fundir(_bloco_ct(0.0, 5.0, sinal=800.0),
                 _bloco_ct(1.5, 8.0, sinal=800.0), esp_mm=3.0, malha=5)
    d = r.get("dentro")
    checar(u"a fusão devolve `dentro`, com a forma da grade, e o laudo "
           u"conta os voxels dela",
           d is not None and np.shape(d) == tuple(reversed(
               r["fixa"].GetSize()))
           and int(np.asarray(d).sum()) == r["laudo"]["n_voxels"],
           u"%s vs %s" % (None if d is None else int(np.asarray(d).sum()),
                          r["laudo"]["n_voxels"]))


def teste_o_laudo_da_tela_tem_acento():
    secao(u"o laudo da tela esta em portugues com acento")
    import radai_elastic_screen as T
    sem_coment = u"\n".join(l for l in T.JS.splitlines()
                            if not l.strip().startswith(u"//"))
    literais = re.findall(r"'((?:[^'\\\n]|\\.)*)'", sem_coment)
    texto = u" ".join(l for l in literais if u" " in l)
    SEM_ACENTO = (u"nao", u"serie", u"series", u"movel", u"rigido",
                  u"rigida", u"minimo", u"maximo", u"sao", u"so",
                  u"necessarias", u"plausivel", u"transformacao")
    achadas = sorted(set(p for p in re.findall(r"[A-Za-z]+", texto)
                         if p.lower() in SEM_ACENTO))
    checar(u"nenhuma palavra sem acento nas strings do JS da tela",
           not achadas, achadas)
    checar(u"  e o veredito que passa é «Transformação plausível»",
           u"Transformação plausível" in T.JS)
    checar(u"  e a tabela do laudo diz mínimo e máximo",
           u"m&iacute;nimo" in T.JS and u"m&aacute;ximo" in T.JS)


def _abdome_ct(gas_em=None, raio_gas=4.0):
    import numpy as np
    import SimpleITK as sitk
    nz, ny, nx = 24, 40, 40
    z, y, x = np.mgrid[0:nz, 0:ny, 0:nx].astype(np.float32)
    v = np.full((nz, ny, nx), -1000.0, dtype=np.float32)
    corpo = ((y - 20) / 17.0) ** 2 + ((x - 20) / 17.0) ** 2 < 1
    v[corpo] = 40.0
    if gas_em is not None:
        zc, yc, xc = gas_em
        v[(z - zc) ** 2 + (y - yc) ** 2 + (x - xc) ** 2 < raio_gas ** 2] = -950.0
    img = sitk.GetImageFromArray(v)
    img.SetSpacing((2.0, 2.0, 2.0))
    return img


def teste_ar_contra_tecido():
    secao(u"ar contra tecido: onde nenhuma deformação é fisicamente correta")
    import numpy as np
    import SimpleITK as sitk
    import radai_elastic as E

    fixa = _abdome_ct(gas_em=(12, 20, 14))
    fund = _abdome_ct()
    dentro = E.mascara_corpo(fixa)
    ar = E.ar_contra_tecido(fixa, fund, dentro)
    checar(u"o gás que só a fixa tem é achado",
           ar["aplica"] and ar["n"] == 1 and ar["regioes"][0]["gas_na"]
           == "fixa", str(ar)[:120])
    esperado = 4.0 / 3.0 * np.pi * (4.0 * 2.0) ** 3 / 1000.0
    checar(u"com o volume da bolha (cerca de %.1f cm³)" % esperado,
           abs(ar["cm3"] - esperado) / esperado < 0.35,
           u"%.2f cm³" % ar["cm3"])
    g = ar["regioes"][0]
    checar(u"e diz ONDE: os cortes da bolha na grade da fusão",
           g["corte_de"] <= 13 <= g["corte_ate"]
           and g["corte_ate"] - g["corte_de"] <= 8,
           u"cortes %d a %d" % (g["corte_de"], g["corte_ate"]))
    ar2 = E.ar_contra_tecido(fund, fixa, dentro)
    checar(u"o gás que só a móvel tem é dito do lado dela",
           ar2["n"] == 1 and ar2["regioes"][0]["gas_na"] == "movel")
    nada = E.ar_contra_tecido(fixa, fixa, dentro)
    checar(u"ISCA: com o mesmo gás nas duas, nada é apontado",
           nada["aplica"] and nada["n"] == 0 and nada["cm3"] == 0.0,
           str(nada))
    a = sitk.GetArrayFromImage(fixa)
    deslocada = sitk.GetImageFromArray(np.roll(a, 1, axis=2))
    deslocada.CopyInformation(fixa)
    borda = E.ar_contra_tecido(fixa, deslocada, dentro)
    checar(u"a casca de um voxel da borda do ar não vira alerta",
           borda["n"] == 0, str(borda)[:120])
    pequena = E.ar_contra_tecido(_abdome_ct(gas_em=(12, 20, 14), raio_gas=1.6),
                                 fund, dentro)
    checar(u"bolha abaixo de %.0f cm³ não vira alerta" % E.AR_MIN_CM3,
           pequena["n"] == 0, str(pequena)[:120])
    ab = sitk.GetArrayFromImage(fund)
    zz, yy, xx = np.mgrid[0:ab.shape[0], 0:ab.shape[1], 0:ab.shape[2]]
    magra_a = np.where(((yy - 20) / 13.0) ** 2 + ((xx - 20) / 13.0) ** 2 < 1,
                       ab, -1000.0).astype(np.float32)
    magra = sitk.GetImageFromArray(magra_a)
    magra.CopyInformation(fund)
    corpo_magra = E.mascara_corpo(magra)
    isca = E.ar_contra_tecido(fund, magra, dentro)
    checar(u"ISCA: sem o corpo da móvel, o ar de FORA na borda da pele vira "
           u"«gás na móvel»", isca["n"] >= 1
           and isca["regioes"][0]["gas_na"] == "movel", str(isca)[:120])
    pele = E.ar_contra_tecido(fund, magra, dentro, corpo_movel=corpo_magra)
    checar(u"com o corpo da móvel, a borda da pele desalinhada não é cavidade",
           pele["n"] == 0, str(pele)[:120])
    dentro_da_magra = E.ar_contra_tecido(
        fund, _abdome_ct(gas_em=(12, 20, 20)), dentro,
        corpo_movel=E.mascara_corpo(_abdome_ct(gas_em=(12, 20, 20))))
    checar(u"e o gás de dentro da móvel continua apontado",
           dentro_da_magra["n"] == 1
           and dentro_da_magra["regioes"][0]["gas_na"] == "movel",
           str(dentro_da_magra)[:120])
    import SimpleITK as _s
    levada = E.levar_mascara(corpo_magra, magra, _s.Euler3DTransform(), fund)
    checar(u"o corpo da móvel é levado à grade da fixa pela transformação",
           levada.shape == corpo_magra.shape
           and bool((levada == corpo_magra).all()))

    l = E.laudo(campo_de(fixa, lambda z, y, x: np.zeros(z.shape + (3,))),
                None, ar=ar)
    checar(u"o laudo chama a atenção e diz os cortes no porquê",
           l["veredito"] == "atencao"
           and any(u"Ar contra tecido" in p and (u"cortes %d a %d"
                   % (g["corte_de"], g["corte_ate"])) in p
                   for p in l["porques"]),
           u" | ".join(l["porques"])[:160])
    sem = E.laudo(campo_de(fixa, lambda z, y, x: np.zeros(z.shape + (3,))),
                  None, ar=nada)
    checar(u"sem região, o mesmo campo passa", sem["veredito"] == "passa",
           sem["veredito"])

    rm = E.fundir(_bloco_ct(0.0, 5.0, sinal=800.0),
                  _bloco_ct(1.5, 8.0, sinal=800.0), esp_mm=3.0, malha=5)
    checar(u"numa RM o alerta não se aplica (HU é só da TC)",
           rm["laudo"]["ar"] == {"aplica": False}, str(rm["laudo"]["ar"]))
    tc = E.fundir(_bloco_ct(0.0, 5.0), _bloco_ct(1.5, 8.0), esp_mm=3.0,
                  malha=5)
    checar(u"entre duas TC a fusão mede e leva ao laudo",
           (tc["laudo"]["ar"] or {}).get("aplica") is True,
           str(tc["laudo"]["ar"])[:100])
    import radai_elastic_screen as ES
    checar(u"a tabela do laudo tem a seção «Ar contra tecido», com os "
           u"cortes clicáveis",
           u"Ar contra tecido" in ES.JS and u"el-ir" in ES.JS
           and u"elIrAoCorte" in ES.JS)


def teste_a_ida_e_volta_interpolada():
    secao(u"a ida-e-volta lida por interpolação, e mostrada ao lado do jacobiano")
    import numpy as np
    import SimpleITK as sitk
    from scipy import ndimage
    import radai_elastic as E
    import radai_elastic_screen as ES

    ref = grade(nz=28, ny=40, nx=40)
    A = 8.0
    c = campo_de(ref, lambda z, y, x: np.stack(
        [A * np.sin(y / 5.0), 0.6 * A * np.cos(x / 6.0),
         0.3 * A * np.sin(z / 4.0)], axis=-1))
    ci = E.inverso(c)
    r = E.consistencia(c, ci)[3:-3, 3:-3, 3:-3]

    d = sitk.GetArrayFromImage(c)
    di = sitk.GetArrayFromImage(ci)
    dest = np.indices(d.shape[:3]).astype(np.float32) + E._desloc_em_indice(c)
    for k in range(3):
        np.clip(dest[k], 0, d.shape[k] - 1, out=dest[k])
    zz, yy, xx = (np.rint(dest[k]).astype(np.int32) for k in range(3))
    vizinho = np.sqrt(((d + di[zz, yy, xx, :]) ** 2).sum(-1))[3:-3, 3:-3, 3:-3]
    p_i, p_v = float(np.percentile(r, 95)), float(np.percentile(vizinho, 95))
    checar(u"interpolada, a ida-e-volta de um campo suave fecha abaixo de "
           u"0,3 mm", p_i < 0.3, u"p95 %.3f mm" % p_i)
    checar(u"ISCA: pelo vizinho mais próximo, o arredondamento sozinho "
           u"inventava 3× mais", p_v > 3.0 * p_i,
           u"vizinho %.3f contra %.3f mm" % (p_v, p_i))
    codigo = sem_docstring(fonte("radai_elastic.py"))
    checar(u"o motor usa interpolação trilinear no inverso",
           "map_coordinates" in codigo and "np.rint" not in codigo)

    checar(u"a vista «ida_e_volta» vem logo depois do jacobiano",
           list(ES.VISTAS).index("ida_e_volta")
           == list(ES.VISTAS).index("jacobiano") + 1)
    checar(u"e, como ele, deriva do campo (sai só com o laudo)",
           "ida_e_volta" in ES.DEPENDEM_DO_CAMPO)
    fundo = np.full((2, 3), 0.5)
    res = np.array([[0.0, ES.IDA_E_VOLTA_PLENA_MM / 2.0,
                     ES.IDA_E_VOLTA_PLENA_MM * 3.0],
                    [np.nan, 0.0, 0.0]])
    rgb = ES.ida_e_volta_em_cor(res, fundo)
    cinza = int(round(0.5 * 255))
    checar(u"resíduo zero é só a anatomia",
           tuple(rgb[0, 0]) == (cinza, cinza, cinza), str(tuple(rgb[0, 0])))
    checar(u"e o resíduo pinta de amarelo, mais forte quanto maior",
           rgb[0, 2, 2] < rgb[0, 1, 2] < cinza and rgb[0, 2, 0] > cinza,
           u"%s %s" % (rgb[0, 1].tolist(), rgb[0, 2].tolist()))
    checar(u"resíduo indefinido aparece como pleno, e não some",
           tuple(rgb[1, 0]) == tuple(rgb[0, 2]), str(rgb[1, 0].tolist()))
    onde = np.array([[True, True, False], [True, True, True]])
    checar(u"fora da região do laudo, só a anatomia",
           tuple(ES.ida_e_volta_em_cor(res, fundo, onde)[0, 2])
           == (cinza, cinza, cinza))
    checar(u"sem campo inverso, a vista mostra a fixa sem cor",
           bool((ES.ida_e_volta_em_cor(None, fundo) == cinza).all()))

    r2 = E.fundir(_bloco_ct(0.0, 5.0, sinal=800.0),
                  _bloco_ct(1.5, 8.0, sinal=800.0), esp_mm=3.0, malha=5)
    cr = r2.get("consist")
    checar(u"a fusão devolve o mapa da ida-e-volta, com a forma da grade",
           cr is not None and np.shape(cr) == tuple(reversed(
               r2["fixa"].GetSize())), str(None if cr is None else cr.shape))
    m = np.asarray(r2["dentro"], bool)
    checar(u"e o p95 do laudo é o desse mesmo mapa (calculado uma vez)",
           cr is not None and abs(float(np.percentile(cr[m], 95))
                                  - r2["laudo"]["consist_p95"]) < 1e-3,
           u"%s" % r2["laudo"]["consist_p95"])
    js = ES.JS
    i_j = js.find(u"<th colspan=2>Jacobiano</th>")
    i_c = js.find(u"<th colspan=2>Ida-e-volta (mm)</th>")
    i_d = js.find(u"<th colspan=2>Deslocamento (mm)</th>")
    checar(u"na tabela do laudo, a ida-e-volta vem logo depois do jacobiano",
           0 <= i_j < i_c < i_d, u"%d %d %d" % (i_j, i_c, i_d))


def teste_nenhum_pedido_espera_para_sempre():
    secao(u"nenhum pedido espera para sempre, e o erro do navegador não aparece")
    import radai_elastic_screen as T
    js = u"\n".join(l for l in T.JS.splitlines()
                    if not l.strip().startswith(u"//"))
    checar(u"há UM lugar que chama fetch", js.count(u"fetch(") == 1,
           u"%d" % js.count(u"fetch("))
    corpo = js.split(u"function elPedir(")[1].split(u"\nfunction ")[0] \
        if u"function elPedir(" in js else u""
    checar(u"e é o `elPedir`, com tempo-limite que aborta o pedido",
           u"fetch(" in corpo and u"setTimeout" in corpo
           and u"abort()" in corpo and u"Promise.race" in corpo)
    checar(u"todo pedido da tela passa por ele",
           js.count(u"elPedir(") >= 10, u"%d" % js.count(u"elPedir("))
    checar(u"ISCA: o erro cru do navegador não vai para a tela",
           u"String(e)" not in js)
    checar(u"a tela diz «O app não respondeu.» e oferece tentar de novo",
           u"O app não respondeu." in js and u'id="el-denovo"' in T.PAGINA
           and u"Tentar de novo" in T.PAGINA and u"elDeNovo" in js)
    checar(u"a fusão é consultada em cadeia, sem pedido empilhado",
           u"setInterval" not in js and u"setTimeout(elPerguntar" in js)
    checar(u"e a busca também", u"setTimeout(elBuscaSeguir" in js)
    checar(u"uma falha solta não interrompe: a tela avisa depois de %s "
           u"seguidas" % u"EL_FALHAS_ATE_AVISAR",
           u"EL_FALHAS_ATE_AVISAR" in js
           and u"elFalhasFusao < EL_FALHAS_ATE_AVISAR" in js)
    pag = T.pagina()
    checar(u"a busca mostra o progresso e tem «Parar a busca» (no popup da série)",
           u'id="el-busca"' in pag and u"Parar a busca" in pag
           and u"pastas olhadas" in pag
           and pag.index(u'id="el_escolha"') < pag.index(u'id="el-busca"'))
    checar(u"e quem pede movimento reduzido vê a barra parada",
           u"prefers-reduced-motion" in T.CSS)
    checar(u"reabrir a tela retoma a busca ou a lista, sem varrer de novo",
           u"function elRetomar" in js
           and u"/api/elastic/varredura?v=" in js)


def teste_o_visor_brilha_enquanto_funde():
    secao(u"o brilho de processamento da casca no visor da fusão")
    import radai_elastic_screen as T
    js = T.JS
    checar(u"a fusão liga o uiCarregando no palco do visor",
           u"window.uiCarregando(p, true" in js
           and u"el('el-palco')" in js.split(u"function elEsperarVisor")[1]
           .split(u"\nfunction ")[0])
    checar(u"e desliga quando a imagem chega",
           u"window.uiCarregando(p, false)" in js
           and u"elEsperarVisor(false)" in js.split(u"function elPerguntar")[1]
           .split(u"\nfunction ")[0])
    checar(u"o laudo não aparece vazio enquanto funde",
           u".el-corpo.esperando .el-laudo{display:none}" in T.CSS)


def teste_o_campo_obrigatorio_treme_e_a_caixa_e_da_casca():
    secao(u"o campo obrigatório treme (C3), e as caixas de marcar são da casca")
    import radai_elastic_screen as T
    js = T.JS

    def corpo(nome):
        if (u"function %s(" % nome) not in js:
            return u""
        return js.split(u"function %s(" % nome)[1].split(u"\nfunction ")[0]
    tremer = corpo(u"elTremer")
    checar(u"o ajudante usa o uiTremer da casca, no campo inteiro",
           u"window.uiTremer(alvo)" in tremer and u".el-campo" in tremer)
    checar(u"  e sem a casca só rola e dá o foco, sem animação própria",
           u"scrollIntoView" in tremer and u"focus()" in tremer
           and u"treme" not in T.CSS)
    varrer = corpo(u"elVarrer")
    checar(u"«Adicionar outra pasta» sem pasta treme o campo da pasta",
           u"elTremer('el-pasta')" in varrer
           and varrer.index(u"elTremer('el-pasta')")
           < varrer.index(u"elPedir("))
    fundir = corpo(u"elFundir")
    checar(u"fixa igual à móvel treme a móvel", u"elTremer('el-movel')" in fundir)
    checar(u"as caixas de marcar ficam com o desenho da casca (nada aqui as "
           u"redesenha)", u"checkbox" not in T.CSS and u"appearance" not in T.CSS)
    checar(u"  na cor do módulo", u"--ui-check-cor:var(--mod-elastic)" in T.CSS)


def _corpo_js(js, nome):
    if (u"function %s(" % nome) not in js:
        return u""
    return js.split(u"function %s(" % nome)[1].split(u"\n}\n")[0]


def _abrir_le_sozinho(js):
    return u"elVarrer(" in _corpo_js(js, u"elRetomar")


def teste_dois_cartoes_e_nada_sozinho():
    secao(u"dois cartões abrem o popup da casca; nada é lido nem fundido sozinho")
    import radai_elastic_screen as T
    p, js = T.pagina(), T.JS
    checar(u"os dois cartões, a deformada e a de destino, nessa ordem",
           0 <= p.find(u'id="el-movel" data-ui-ps-abre="el_escolha" data-ui-ps-ctx="movel"')
           < p.find(u'id="el-fixa" data-ui-ps-abre="el_escolha" data-ui-ps-ctx="fixa"')
           and T.CARTAO_MOVEL == u"Carregar imagem a ser deformada"
           and T.CARTAO_FIXA == u"Carregar imagem de destino")
    checar(u"  e os dois seletores de série saíram", u"<select id=\"el-fixa\"" not in p
           and u"<select id=\"el-movel\"" not in p)
    checar(u"o popup é o padrão da casca, com o acervo e a pasta, sem abrir sozinho",
           u'<div class="ui-ps" id="el_escolha" data-ui-ps' in p
           and u'data-guia="acervo"' in p and u'data-guia="pasta"' in p
           and u"data-sozinho" not in p.split(u'id="el_escolha"')[1][:200])
    checar(u"reabrir a tela retoma a lista ou a busca, e NÃO varre a pasta favorita",
           u"function elRetomar" in js and not _abrir_le_sozinho(js))
    isca = js.replace(u"elV=d.v; elBuscaMostrar(true); elBuscaContar(d); elBuscaSeguir() }",
                      u"elV=d.v; elBuscaMostrar(true); elBuscaContar(d); elBuscaSeguir(); return }\n"
                      u"    if(!(d.series||[]).length) elVarrer(false);")
    checar(u"  (isca) com a varredura do ROOT de volta, é acusado",
           isca != js and _abrir_le_sozinho(isca))
    lib = _corpo_js(js, u"elLiberarFundir")
    checar(u"«Fundir» só liga com as DUAS escolhidas, e a fusão só pelo clique",
           u"!elB('fixa') || !elB('movel')" in lib
           and js.replace(u"function elFundir()", u"").count(u"elFundir()") == 0 and u"addEventListener('click', elFundir)" in js)
    esc = _corpo_js(js, u"elEscolher")
    checar(u"escolher põe a série no cartão de quem abriu o popup, e fecha o popup",
           u"p.contexto()" in esc and u"EL_SEL[qual] = {b: b" in esc
           and u"uiCartaoRotulo('el-' + qual" in esc and u"p.fechar()" in esc)
    checar(u"  a série vai por bilhete (o do acervo também), nunca por caminho",
           u"linha.bilhete" in _corpo_js(js, u"elTabelaLigar")
           and u"pasta" not in esc)


def teste_a_demo_saiu_do_elastic():
    secao(u"a demo saiu do Elastic RT")
    import radai_elastic_screen as T
    tela = sem_docstring(fonte("radai_elastic_screen.py"))
    checar(u"a tela não usa o módulo da demo", u"radai_demo" not in tela)
    checar(u"nem pinta linha DEMO", u"DEMO" not in T.pagina())
    checar(u"e a recusa de misturar demo com paciente saiu junto",
           not hasattr(T, "recusa_da_mistura") and not hasattr(T, "com_a_demo"))


def _rotulos_divergentes(d, codigos, ajuda, rotulos):
    import radai_phrases as F
    fora = []
    for c in codigos:
        tr = d[c].get(F.normalizar(ajuda), u"")
        for r in rotulos:
            nome = d[c].get(F.normalizar(r), r)
            if nome not in tr:
                fora.append(u"%s: %s" % (c, nome))
    return fora


def teste_a_dica_cita_o_botao_com_o_nome_dele():
    secao(u"TEL-15: a dica da lista cita os botões pelo mesmo nome, nos onze idiomas")
    import radai_phrases as F
    d = F.construir()
    ajuda = (u"«Procurar séries» substitui a lista; «Adicionar outra "
             u"pasta» soma a ela. As duas séries da fusão não precisam estar "
             u"na mesma pasta.")
    rotulos = (u"Procurar séries", u"Adicionar outra pasta")
    fora = _rotulos_divergentes(d, F.CODIGOS, ajuda, rotulos)
    checar(u"a tradução da dica traz o rótulo traduzido de cada botão", not fora,
           u" | ".join(fora))
    isca = dict(d)
    isca["en"] = dict(d["en"])
    k = F.normalizar(ajuda)
    isca["en"][k] = isca["en"][k].replace(u"Find series", u"Search series")
    checar(u"  (isca) «Search series» contra o botão «Find series» é acusado",
           _rotulos_divergentes(isca, [u"en"], ajuda, rotulos) == [u"en: Find series"])


def main():
    print(u"=" * 68)
    print(u"  ELASTIC RT — a fusão elástica, e o laudo que sai junto com ela")
    print(u"=" * 68)
    for f in (teste_a_medida_mede, teste_o_reprova_acende,
              teste_a_ida_e_volta, teste_a_direcao_obliqua,
              teste_a_mascara_do_corpo, teste_a_trava_da_imagem,
              teste_nao_propaga_e_nao_exporta, teste_nada_e_detectado,
              teste_o_caminho_nao_viaja_em_get, teste_uma_fusao_por_vez,
              teste_a_suite_conhece_o_modulo, teste_a_tela_monta,
              teste_o_cartao_nao_anuncia_obra_que_acabou,
              teste_a_lista_acumula_pastas,
              teste_a_varredura_e_a_da_suite,
              teste_as_rotas_de_pasta_executam,
              teste_a_busca_mostra_o_que_acha_e_para,
              teste_o_ciclo_roda,
              teste_a_rm_nao_e_tc, teste_o_jacobiano_olha_a_direcao,
              teste_o_veredito_nao_inventa_compressao,
              teste_a_partida_do_rigido, teste_a_cobertura,
              teste_a_serie_certa_da_pasta, teste_a_tela_da_rm,
              teste_o_ciclo_de_rm, teste_a_rota_da_fusao_executa,
              teste_a_metrica_olha_o_corpo, teste_a_dobra_diz_o_que_tentar,
              teste_o_mapa_e_o_numero_sao_da_mesma_regiao,
              teste_o_laudo_da_tela_tem_acento,
              teste_ar_contra_tecido, teste_a_ida_e_volta_interpolada,
              teste_nenhum_pedido_espera_para_sempre,
              teste_o_visor_brilha_enquanto_funde,
              teste_o_campo_obrigatorio_treme_e_a_caixa_e_da_casca,
              teste_a_demo_saiu_do_elastic,
              teste_a_dica_cita_o_botao_com_o_nome_dele,
              teste_dois_cartoes_e_nada_sozinho):
        try:
            f()
        except Exception as e:
            import traceback
            checar(u"%s nao levantou" % f.__name__, False,
                   u"%s: %s" % (type(e).__name__, e))
            if VERBOSO:
                traceback.print_exc()

    maus = [n for n, ok, _d in _RES if not ok]
    print(u"\n" + u"=" * 68)
    if maus:
        print(u"FALHOU: %d de %d checagens" % (len(maus), len(_RES)))
        for n in maus:
            print(u"  - %s" % n)
        print(u"=" * 68)
        return 1
    print(u"OK: %d checagens, todas passaram" % len(_RES))
    print(u"=" * 68)
    return 0


if __name__ == "__main__":
    sys.exit(main())
