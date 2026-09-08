
from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]; R=ROOT/"results"; F=ROOT/"figures"; F.mkdir(parents=True,exist_ok=True)

acc=pd.read_csv(R/"accuracy_by_model_variant.csv")
p=acc.pivot(index="variant_type",columns="model",values="accuracy").reindex(["original","lexical","syntactic","information_order"])
ax=p.plot(kind="bar",figsize=(10,6)); ax.set_ylabel("Accuracy"); ax.set_xlabel("Input condition"); ax.set_title("Accuracy by Linguistic Transformation")
plt.tight_layout(); plt.savefig(F/"accuracy_by_transformation.png",dpi=220,bbox_inches="tight"); plt.close()

pairs=pd.read_csv(R/"paired_robustness_results.csv"); q=pairs[pairs.dataset=="ALL"]
h=q.pivot(index="model",columns="variant_type",values="correctness_flip_rate").reindex(columns=["lexical","syntactic","information_order"])
fig,ax=plt.subplots(figsize=(8,5)); im=ax.imshow(h.values,aspect="auto"); ax.set_xticks(range(len(h.columns))); ax.set_xticklabels(h.columns,rotation=20,ha="right")
ax.set_yticks(range(len(h.index))); ax.set_yticklabels(h.index); ax.set_title("Correctness Flip Rate")
for i in range(len(h.index)):
    for j in range(len(h.columns)): ax.text(j,i,f"{100*h.iloc[i,j]:.1f}%",ha="center",va="center")
fig.colorbar(im,ax=ax,label="Flip rate"); plt.tight_layout(); plt.savefig(F/"flip_rate_heatmap.png",dpi=220,bbox_inches="tight"); plt.close()

rob=pd.read_csv(R/"robust_accuracy_results.csv"); r=rob[rob.dataset=="ALL"].set_index("model")[["original_accuracy","robust_accuracy_core"]]
ax=r.plot(kind="bar",figsize=(9,6)); ax.set_ylabel("Accuracy"); ax.set_xlabel("Model"); ax.set_title("Original vs Core Robust Accuracy")
plt.tight_layout(); plt.savefig(F/"original_vs_robust_accuracy.png",dpi=220,bbox_inches="tight"); plt.close()

print("[done] figures created in",F)
