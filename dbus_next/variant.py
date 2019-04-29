from . import signature as s


class Variant:
    def __init__(self, signature, value):
        signature_str = ''
        signature_tree = None
        signature_type = None

        if type(signature) is s.SignatureTree:
            signature_tree = signature
        elif type(signature) is s.SignatureType:
            signature_type = signature
            signature_str = signature.signature
        elif type(signature) is str:
            signature_tree = s.SignatureTree(signature)
        else:
            raise TypeError('signature must be a SignatureTree, SignatureType, or a string')

        if signature_tree:
            if len(signature_tree.types) != 1:
                raise ValueError('variants must have a signature for a single complete type')
            signature_str = signature_tree.signature
            signature_type = signature_tree.types[0]

        signature_type.verify(value)

        self.type = signature_type
        self.signature = signature_str
        self.value = value

    def __eq__(self, other):
        if type(other) is Variant:
            return self.signature == other.signature and self.value == other.value
        else:
            return super().__eq__(other)
