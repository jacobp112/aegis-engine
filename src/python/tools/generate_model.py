import onnx
from onnx import helper, TensorProto
import numpy as np

def create_risk_model():
    print("Generating Risk Scoring Model (aegis_risk_model.onnx)...")

    # Define inputs: 'features' (Batch x 10)
    # Features might be: [name_len, has_number, region_code, ... ]
    input_info = helper.make_tensor_value_info('features', TensorProto.FLOAT, [None, 10])

    # Define output: 'risk_score' (Batch x 1)
    output_info = helper.make_tensor_value_info('risk_score', TensorProto.FLOAT, [None, 1])

    # Define weights for Linear Regression (Matrix Mul)
    # 10x1 Matrix
    weights_data = np.array([
        [0.5], [0.2], [-0.1], [0.8], [0.1],
        [0.0], [0.0], [0.9],  [0.3], [0.1]
    ], dtype=np.float32).flatten().tolist()

    weights_init = helper.make_tensor(
        name='weights',
        data_type=TensorProto.FLOAT,
        dims=[10, 1],
        vals=weights_data
    )

    # Bias
    bias_init = helper.make_tensor(
        name='bias',
        data_type=TensorProto.FLOAT,
        dims=[1],
        vals=[0.05]
    )

    # Nodes: MatMul + Add
    node_matmul = helper.make_node(
        'MatMul',
        inputs=['features', 'weights'],
        outputs=['matmul_out']
    )

    node_add = helper.make_node(
        'Add',
        inputs=['matmul_out', 'bias'],
        outputs=['risk_score']
    )

    # Graph
    graph_def = helper.make_graph(
        [node_matmul, node_add],
        'RiskScoringGraph',
        [input_info],
        [output_info],
        [weights_init, bias_init]
    )

    # Model
    model_def = helper.make_model(graph_def, producer_name='aegis_ai')

    # Save
    onnx.save(model_def, 'aegis_risk_model.onnx')
    print("Model saved to aegis_risk_model.onnx")

if __name__ == "__main__":
    try:
        create_risk_model()
    except ImportError:
        print("Error: 'onnx' library not found. Please install with: pip install onnx numpy")
