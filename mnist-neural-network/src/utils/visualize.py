"""
visualize.py

Lee los resultados guardados por src/scratch/train.py y
src/pytorch_version/train.py, y genera tres graficos en results/:

1. accuracy_comparison.png    -> curva de precision por epoca, ambas versiones
2. confusion_matrix.png       -> matriz de confusion de la version PyTorch
3. misclassified_examples.png -> ejemplos donde la red se equivoco
"""

import json
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from sklearn.metrics import confusion_matrix

# Ruta absoluta basada en la ubicacion de este archivo, para que
# funcione sin importar desde donde ejecutes el script.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RESULTS_DIR = PROJECT_ROOT / "results"
DATA_DIR = PROJECT_ROOT / "data"


def plot_accuracy_comparison():
    """
    Grafica, en un mismo eje, como fue subiendo la precision de la
    version NumPy y la version PyTorch a lo largo de las epocas.
    """
    scratch = np.load(RESULTS_DIR / "scratch_results.npz")
    with open(RESULTS_DIR / "pytorch_results.json") as f:
        pytorch = json.load(f)

    scratch_history = scratch["history"] * 100
    pytorch_history = np.array(pytorch["history"]) * 100

    plt.figure(figsize=(9, 5))
    plt.plot(range(1, len(scratch_history) + 1), scratch_history,
              marker="o", markersize=3, label="Desde cero (NumPy)")
    plt.plot(range(1, len(pytorch_history) + 1), pytorch_history,
              marker="o", markersize=3, label="PyTorch")
    plt.xlabel("Epoca")
    plt.ylabel("Precision en test (%)")
    plt.title("Precision por epoca: NumPy vs PyTorch")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "accuracy_comparison.png", dpi=150)
    plt.close()
    print("Guardado: results/accuracy_comparison.png")


def plot_confusion_matrix():
    """
    Matriz de confusion de la version PyTorch (la de mejor precision):
    muestra, para cada digito real, que digitos predijo la red.
    La diagonal son los aciertos; fuera de la diagonal son los errores.
    """
    with open(RESULTS_DIR / "pytorch_results.json") as f:
        pytorch = json.load(f)

    y_true = pytorch["y_true"]
    y_pred = pytorch["y_pred"]
    cm = confusion_matrix(y_true, y_pred)

    plt.figure(figsize=(7, 6))
    plt.imshow(cm, cmap="Blues")
    plt.colorbar(label="Cantidad de ejemplos")
    plt.xticks(range(10))
    plt.yticks(range(10))
    plt.xlabel("Digito predicho")
    plt.ylabel("Digito real")
    plt.title("Matriz de confusion (version PyTorch)")

    for i in range(10):
        for j in range(10):
            color = "white" if cm[i, j] > cm.max() / 2 else "black"
            plt.text(j, i, str(cm[i, j]), ha="center", va="center",
                      color=color, fontsize=8)

    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "confusion_matrix.png", dpi=150)
    plt.close()
    print("Guardado: results/confusion_matrix.png")


def plot_misclassified_examples(n_examples=10):
    """
    Muestra 'n_examples' imagenes de test donde la red PyTorch se
    equivoco, junto con la etiqueta real y la predicha.
    """
    from torchvision import datasets, transforms

    with open(RESULTS_DIR / "pytorch_results.json") as f:
        pytorch = json.load(f)

    y_true = np.array(pytorch["y_true"])
    y_pred = np.array(pytorch["y_pred"])
    wrong_indices = np.where(y_true != y_pred)[0][:n_examples]

    transform = transforms.Compose([transforms.ToTensor()])
    test_dataset = datasets.MNIST(root=str(DATA_DIR), train=False,
                                    download=True, transform=transform)

    cols = 5
    rows = (len(wrong_indices) + cols - 1) // cols
    plt.figure(figsize=(cols * 2, rows * 2.6))

    for i, idx in enumerate(wrong_indices):
        image, _ = test_dataset[idx]
        plt.subplot(rows, cols, i + 1)
        plt.imshow(image.squeeze(), cmap="gray")
        plt.title(f"Real: {y_true[idx]} / Pred: {y_pred[idx]}", fontsize=9)
        plt.axis("off")

    plt.suptitle("Ejemplos mal clasificados (version PyTorch)")
    # hspace mas grande deja espacio vertical entre filas para que los
    # titulos de una fila no se superpongan con las imagenes de arriba
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    plt.subplots_adjust(hspace=0.5)
    plt.savefig(RESULTS_DIR / "misclassified_examples.png", dpi=150)
    plt.close()
    print("Guardado: results/misclassified_examples.png")


if __name__ == "__main__":
    plot_accuracy_comparison()
    plot_confusion_matrix()
    plot_misclassified_examples()