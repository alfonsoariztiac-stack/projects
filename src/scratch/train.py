"""
train.py

Entrena la red neuronal desde cero con MNIST, y guarda los resultados
(historial de precision, pesos entrenados, predicciones sobre el test
set) en la carpeta results/, para que visualize.py los pueda usar
despues sin necesidad de reentrenar.
"""

from pathlib import Path

import numpy as np

from mnist_loader import load_data
from network import Network

# Ruta absoluta a la carpeta results/, calculada a partir de la
# ubicacion de ESTE archivo (no depende de desde donde ejecutes el
# script). __file__ es la ruta a train.py; .parent tres veces sube
# de src/scratch/ -> src/ -> raiz del proyecto -> results/
RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "results"


def main():
    print("Cargando datos...")
    training_data, test_data = load_data()

    net = Network([784, 16, 16, 10])

    history = net.SGD(
        training_data,
        epochs=30,
        mini_batch_size=10,
        learning_rate=3.0,
        test_data=test_data
    )

    print("Entrenamiento terminado. Calculando predicciones finales...")
    _, y_true, y_pred = net.evaluate_with_predictions(test_data)

    print(f"Guardando resultados en {RESULTS_DIR / 'scratch_results.npz'} ...")
    np.savez(
        RESULTS_DIR / "scratch_results.npz",
        history=np.array(history),
        y_true=y_true,
        y_pred=y_pred,
        weight_0=net.weights[0], bias_0=net.biases[0],
        weight_1=net.weights[1], bias_1=net.biases[1],
        weight_2=net.weights[2], bias_2=net.biases[2],
    )
    print("Listo.")


if __name__ == "__main__":
    main()