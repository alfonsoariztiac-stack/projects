"""
mnist_loader.py

Descarga el dataset MNIST y lo prepara en el formato que necesita
nuestra red neuronal: vectores de 784 valores (imagenes aplanadas,
normalizadas entre 0 y 1) y etiquetas en formato one-hot.
"""

import numpy as np
from pathlib import Path
from sklearn.datasets import fetch_openml

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"


def load_data():
    """
    Descarga MNIST (o lo carga desde cache local si ya se descargo antes)
    y devuelve dos listas:

    - training_data: 60,000 tuplas (x, y)
    - test_data: 10,000 tuplas (x, y)

    x es un vector columna de forma (784, 1) con valores entre 0 y 1.
    En training_data, y es un vector columna one-hot de forma (10, 1).
    En test_data, y es simplemente el digito correcto (un entero),
    para poder comparar facil contra la prediccion de la red.
    """
    print("Descargando/cargando MNIST (puede tardar la primera vez)...")
    mnist = fetch_openml(
        "mnist_784", version=1, as_frame=False, data_home=str(DATA_DIR)
    )
    X, y = mnist["data"], mnist["target"].astype(int)

    # Normalizar pixeles: de [0, 255] a [0, 1]
    X = X / 255.0

    # Separar en entrenamiento (60,000) y test (10,000)
    X_train, X_test = X[:60000], X[60000:]
    y_train, y_test = y[:60000], y[60000:]

    training_data = [
        (x.reshape(784, 1), vectorized_result(label))
        for x, label in zip(X_train, y_train)
    ]

    test_data = [
        (x.reshape(784, 1), label)
        for x, label in zip(X_test, y_test)
    ]

    return training_data, test_data


def vectorized_result(digit):
    """
    Convierte un digito (por ejemplo 3) en un vector one-hot de 10
    posiciones: [0,0,0,1,0,0,0,0,0,0], en forma de vector columna (10, 1).

    Esto es lo que la red va a intentar predecir: activar SOLO la
    neurona de salida correspondiente al digito correcto (la idea
    del video 1: la ultima capa tiene 10 neuronas, una por digito).
    """
    e = np.zeros((10, 1))
    e[digit] = 1.0
    return e


if __name__ == "__main__":
    training_data, test_data = load_data()
    print(f"Ejemplos de entrenamiento: {len(training_data)}")
    print(f"Ejemplos de test: {len(test_data)}")
    x, y = training_data[0]
    print(f"Forma de una imagen: {x.shape}")
    print(f"Forma de una etiqueta (one-hot): {y.shape}")