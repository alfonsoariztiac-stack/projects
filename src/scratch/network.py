"""
network.py

Define la arquitectura de la red neuronal: como se inicializan los
pesos y biases, y como una imagen "fluye" hacia adelante a traves
de las capas hasta producir una prediccion (feedforward).
"""

import numpy as np


class Network:
    def __init__(self, sizes):
        """
        sizes: lista con el numero de neuronas en cada capa.
        Ejemplo: [784, 16, 16, 10] significa:
          - capa de entrada: 784 neuronas
          - dos capas ocultas de 16 neuronas cada una
          - capa de salida: 10 neuronas

        Los biases y pesos se inicializan al azar (distribucion normal
        estandar). Esto es justo lo que dice el video 1: al principio
        la red no sabe nada, sus pesos son aleatorios.
        """
        self.num_layers = len(sizes)
        self.sizes = sizes

        # Un bias por neurona, en cada capa EXCEPTO la de entrada
        # (la capa de entrada no tiene bias, solo recibe los pixeles)
        self.biases = [np.random.randn(y, 1) for y in sizes[1:]]

        # Una matriz de pesos entre cada par de capas consecutivas.
        # weights[0] conecta la capa 0 (entrada) con la capa 1 (primera oculta).
        # Su forma es (neuronas_capa_siguiente, neuronas_capa_anterior).
        self.weights = [np.random.randn(y, x)
                         for x, y in zip(sizes[:-1], sizes[1:])]

    def feedforward(self, a):
        """
        Toma un vector de entrada 'a' (forma (784, 1)) y lo pasa por
        todas las capas de la red, devolviendo el vector de salida
        final (forma (10, 1)).

        Para cada capa se calcula:
            z = w . a + b       (combinacion lineal de pesos, entrada y bias)
            a = sigmoid(z)      (funcion de activacion)

        Esta es la formula que 3Blue1Brown escribe en el video 1:
        a' = sigma(W a + b)
        """
        for b, w in zip(self.biases, self.weights):
            a = sigmoid(np.dot(w, a) + b)
        return a

    def predict(self, a):
        """
        Devuelve el digito predicho (0-9): la posicion de la neurona
        de salida con mayor activacion.
        """
        output = self.feedforward(a)
        return int(np.argmax(output))


def sigmoid(z):
    """
    Funcion de activacion sigmoide: aplasta cualquier numero real
    al rango (0, 1). Se usa para que la activacion de cada neurona
    se pueda interpretar como "que tan encendida" esta, de forma
    similar a una neurona biologica.
    """
    return 1.0 / (1.0 + np.exp(-z))


if __name__ == "__main__":
    from mnist_loader import load_data

    net = Network([784, 16, 16, 10])

    training_data, test_data = load_data()
    x, y_true = test_data[0]

    prediction = net.predict(x)
    output = net.feedforward(x)

    print(f"Digito real: {y_true}")
    print(f"Prediccion de la red (sin entrenar): {prediction}")
    print(f"Activaciones de salida: {output.flatten()}")
    print("(Como los pesos son aleatorios, es normal que la prediccion este mal)")