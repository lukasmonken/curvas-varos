import formulas, time, json, sys
sys.setrecursionlimit(100000)
t=time.time()
xl=formulas.ExcelModel().loads('docs/legado/Query-Avila.xlsx').finish()
print('loaded',time.time()-t, flush=True)
sol=xl.calculate()
print('calc',time.time()-t, flush=True)
xl.write(dirpath='scratch/recalc')
print('written',time.time()-t)
