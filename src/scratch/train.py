"""
train.py

Script principal para entrenar la red neuronal desde cero con MNIST.
"""

from mnist_loader import load_data
from network import Network


def main():
    print("Cargando datos...")
    training_data, test_data = load_data()

    net = Network([784, 16, 16, 10])

    net.SGD(
        training_data,
        epochs=30,
        mini_batch_size=10,
        learning_rate=3.0,
        test_data=test_data
    )


if __name__ == "__main__":
    main()