"""
network.py

Define la arquitectura de la red neuronal, el feedforward, backprop
y el entrenamiento con descenso de gradiente estocastico (SGD).
Ahora tambien guarda el historial de precision durante el entrenamiento.
"""

import random
import numpy as np


class Network:
    def __init__(self, sizes):
        self.num_layers = len(sizes)
        self.sizes = sizes
        self.biases = [np.random.randn(y, 1) for y in sizes[1:]]
        self.weights = [np.random.randn(y, x)
                         for x, y in zip(sizes[:-1], sizes[1:])]

    def feedforward(self, a):
        for b, w in zip(self.biases, self.weights):
            a = sigmoid(np.dot(w, a) + b)
        return a

    def predict(self, a):
        output = self.feedforward(a)
        return int(np.argmax(output))

    def cost_derivative(self, output_activations, y):
        return output_activations - y

    def backprop(self, x, y):
        nabla_b = [np.zeros(b.shape) for b in self.biases]
        nabla_w = [np.zeros(w.shape) for w in self.weights]

        activation = x
        activations = [x]
        zs = []

        for b, w in zip(self.biases, self.weights):
            z = np.dot(w, activation) + b
            zs.append(z)
            activation = sigmoid(z)
            activations.append(activation)

        delta = self.cost_derivative(activations[-1], y) * sigmoid_prime(zs[-1])
        nabla_b[-1] = delta
        nabla_w[-1] = np.dot(delta, activations[-2].transpose())

        for l in range(2, self.num_layers):
            z = zs[-l]
            sp = sigmoid_prime(z)
            delta = np.dot(self.weights[-l + 1].transpose(), delta) * sp
            nabla_b[-l] = delta
            nabla_w[-l] = np.dot(delta, activations[-l - 1].transpose())

        return nabla_b, nabla_w

    def update_mini_batch(self, mini_batch, learning_rate):
        nabla_b = [np.zeros(b.shape) for b in self.biases]
        nabla_w = [np.zeros(w.shape) for w in self.weights]

        for x, y in mini_batch:
            delta_nabla_b, delta_nabla_w = self.backprop(x, y)
            nabla_b = [nb + dnb for nb, dnb in zip(nabla_b, delta_nabla_b)]
            nabla_w = [nw + dnw for nw, dnw in zip(nabla_w, delta_nabla_w)]

        m = len(mini_batch)
        self.weights = [w - (learning_rate / m) * nw
                         for w, nw in zip(self.weights, nabla_w)]
        self.biases = [b - (learning_rate / m) * nb
                        for b, nb in zip(self.biases, nabla_b)]

    def evaluate(self, test_data):
        results = [(self.predict(x), y) for x, y in test_data]
        return sum(int(pred == y) for pred, y in results)

    def evaluate_with_predictions(self, test_data):
        """
        Igual que evaluate(), pero ademas devuelve la lista completa
        de predicciones y etiquetas reales. La usamos despues para
        armar la matriz de confusion y encontrar ejemplos mal
        clasificados (no se necesita durante el entrenamiento normal,
        solo al final para analizar resultados).
        """
        y_true = []
        y_pred = []
        for x, y in test_data:
            y_true.append(y)
            y_pred.append(self.predict(x))
        correct = sum(int(p == t) for p, t in zip(y_pred, y_true))
        return correct, np.array(y_true), np.array(y_pred)

    def SGD(self, training_data, epochs, mini_batch_size, learning_rate, test_data=None):
        """
        Entrena la red con descenso de gradiente estocastico.
        Devuelve 'history': una lista con la precision (0.0 a 1.0)
        obtenida al final de cada epoca, para poder graficarla despues.
        """
        n = len(training_data)
        training_data = list(training_data)
        history = []

        for epoch in range(epochs):
            random.shuffle(training_data)
            mini_batches = [
                training_data[k:k + mini_batch_size]
                for k in range(0, n, mini_batch_size)
            ]

            for mini_batch in mini_batches:
                self.update_mini_batch(mini_batch, learning_rate)

            if test_data:
                accuracy = self.evaluate(test_data)
                history.append(accuracy / len(test_data))
                print(f"Epoca {epoch + 1}/{epochs}: {accuracy}/{len(test_data)} "
                      f"correctos ({100 * accuracy / len(test_data):.2f}%)")
            else:
                print(f"Epoca {epoch + 1}/{epochs} completa")

        return history


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def sigmoid_prime(z):
    s = sigmoid(z)
    return s * (1 - s)