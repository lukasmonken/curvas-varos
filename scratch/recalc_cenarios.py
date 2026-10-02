"""Prova de recálculo do motor `formulas`: altera mês/trimestre e compara com scratch/indep.py."""
import formulas, sys, json
sys.setrecursionlimit(100000)
xl = formulas.ExcelModel().loads('docs/legado/Query-Avila.xlsx').finish()
book = "[Query-Avila.xlsx]"
def cell(sheet, ref): return f"'{book}{sheet.upper()}'!{ref}"
keys = [k for k in xl.dsp.data_nodes if isinstance(k, str) and k.endswith('!C2') and 'DI' in k.upper()]
print('exemplo de id:', keys[:3])
out = {}
for mes, tri in [('Agosto', '3º Tri'), ('Setembro', '3º Tri')]:
    inputs = {cell(s, 'C2'): mes for s in ('DI', 'INFLAÇÃO')}
    inputs.update({cell(s, 'C3'): tri for s in ('DI', 'INFLAÇÃO')})
    sol = xl.calculate(inputs=inputs)
    def v(s, r):
        x = sol[cell(s, r)].value
        return float(x.ravel()[0]) if hasattr(x, 'ravel') else x
    out[mes] = dict(ytg=v('DI','R26'), di_S26=v('DI','S26'), di_E4=v('DI','E4'), di_S27=v('DI','S27'),
                    inf_S27=v('INFLAÇÃO','S27'), di_2027=v('DI','F4'), inf_2027=v('INFLAÇÃO','F4'))
    print(mes, tri, json.dumps(out[mes]))
json.dump(out, open('scratch/recalc/cenarios_formulas.json', 'w'), indent=1)
