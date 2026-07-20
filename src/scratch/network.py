"""
network.py

Define la arquitectura de la red neuronal, el feedforward, y ahora
tambien backpropagation y el entrenamiento con descenso de gradiente
estocastico (SGD).
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
        """
        Derivada de la funcion de costo respecto a las activaciones
        de la capa de salida. Usamos costo cuadratico (MSE):
            C = 1/2 * sum((a - y)^2)
        Su derivada respecto a 'a' es simplemente (a - y): mientras
        mas lejos esta la activacion del valor correcto, mas grande
        (y en la direccion correcta) es esta derivada.
        """
        return output_activations - y

    def backprop(self, x, y):
        """
        Devuelve (nabla_b, nabla_w): el gradiente de la funcion de
        costo respecto a CADA bias y CADA peso de la red, para un
        solo ejemplo (x, y). "Gradiente" aqui significa: en que
        direccion y que tanto hay que mover cada peso/bias para
        reducir el error.
        """
        nabla_b = [np.zeros(b.shape) for b in self.biases]
        nabla_w = [np.zeros(w.shape) for w in self.weights]

        # ---- FEEDFORWARD (igual que antes, pero guardando todo) ----
        activation = x
        activations = [x]   # activaciones de cada capa, incluyendo la entrada
        zs = []              # valores z (antes de aplicar sigmoid) de cada capa

        for b, w in zip(self.biases, self.weights):
            z = np.dot(w, activation) + b
            zs.append(z)
            activation = sigmoid(z)
            activations.append(activation)

        # ---- BACKWARD PASS ----
        # Empezamos por la capa de SALIDA: cuanto error tiene cada
        # neurona de salida (delta), combinando la derivada del costo
        # con la derivada de la sigmoide.
        delta = self.cost_derivative(activations[-1], y) * sigmoid_prime(zs[-1])
        nabla_b[-1] = delta
        nabla_w[-1] = np.dot(delta, activations[-2].transpose())

        # Ahora propagamos ese error hacia atras, capa por capa,
        # usando los pesos para "repartir la culpa" a la capa anterior.
        # Esta es la idea central del video 3: el error de una capa
        # depende del error de la capa siguiente, ponderado por los
        # pesos que las conectan.
        for l in range(2, self.num_layers):
            z = zs[-l]
            sp = sigmoid_prime(z)
            delta = np.dot(self.weights[-l + 1].transpose(), delta) * sp
            nabla_b[-l] = delta
            nabla_w[-l] = np.dot(delta, activations[-l - 1].transpose())

        return nabla_b, nabla_w

    def update_mini_batch(self, mini_batch, learning_rate):
        """
        Ajusta los pesos y biases de la red usando el promedio del
        gradiente calculado sobre un mini-lote de ejemplos (no sobre
        UN solo ejemplo, ni sobre TODOS a la vez -- ese equilibrio es
        justo lo que hace que "estocastico" sea mas rapido que
        descenso de gradiente clasico).
        """
        nabla_b = [np.zeros(b.shape) for b in self.biases]
        nabla_w = [np.zeros(w.shape) for w in self.weights]

        for x, y in mini_batch:
            delta_nabla_b, delta_nabla_w = self.backprop(x, y)
            nabla_b = [nb + dnb for nb, dnb in zip(nabla_b, delta_nabla_b)]
            nabla_w = [nw + dnw for nw, dnw in zip(nabla_w, delta_nabla_w)]

        m = len(mini_batch)
        # El "paso" de ajuste: nos movemos en direccion CONTRARIA al
        # gradiente (por eso el signo menos), escalado por el learning_rate.
        self.weights = [w - (learning_rate / m) * nw
                         for w, nw in zip(self.weights, nabla_w)]
        self.biases = [b - (learning_rate / m) * nb
                        for b, nb in zip(self.biases, nabla_b)]

    def evaluate(self, test_data):
        """Cuenta cuantos ejemplos de test_data la red clasifica bien."""
        results = [(self.predict(x), y) for x, y in test_data]
        return sum(int(pred == y) for pred, y in results)

    def SGD(self, training_data, epochs, mini_batch_size, learning_rate, test_data=None):
        """
        Entrena la red con descenso de gradiente estocastico.

        - epochs: cuantas veces se recorre TODO el training_data
        - mini_batch_size: cuantos ejemplos se usan por cada ajuste de pesos
        - learning_rate: que tan grande es cada paso de ajuste
        - test_data: si se pasa, se mide el desempeno despues de cada epoca
        """
        n = len(training_data)
        training_data = list(training_data)

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
                print(f"Epoca {epoch + 1}/{epochs}: {accuracy}/{len(test_data)} "
                      f"correctos ({100 * accuracy / len(test_data):.2f}%)")
            else:
                print(f"Epoca {epoch + 1}/{epochs} completa")


def sigmoid(z):
    """Aplasta cualquier numero real al rango (0, 1)."""
    return 1.0 / (1.0 + np.exp(-z))


def sigmoid_prime(z):
    """
    Derivada de la sigmoide. Se necesita en backprop porque, por
    regla de la cadena, para saber como el costo cambia respecto a z
    (antes de aplicar sigmoid), hay que multiplicar por que tan
    "sensible" es la sigmoide en ese punto.
    """
    s = sigmoid(z)
    return s * (1 - s)