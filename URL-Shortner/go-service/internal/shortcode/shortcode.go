package shortcode

const alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"

const base = int64(len(alphabet))

func Encode(n int64) string {
	if n == 0 {
		return string(alphabet[0])
	}

	var digits []byte
	for n > 0 {
		rem := n % base
		n = n / base
		digits = append(digits, alphabet[rem])
	}

	for i, j := 0, len(digits)-1; i < j; i, j = i+1, j-1 {
		digits[i], digits[j] = digits[j], digits[i]
	}

	return string(digits)
}
