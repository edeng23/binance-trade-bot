import React, {useEffect, useState} from 'react';
import axios, {AxiosResponse} from 'axios';
import styled from 'styled-components';
import {CoinContract} from "./CoinContract";
import Coin from "./Coin";


const BackendRoute = 'http://localhost:5123'

const MyCoinList = () => {
    const [coins, setCoins] = useState<Array<CoinContract>>([]);

    useEffect(() => {
        axios
            .get(`${BackendRoute}/api/coins`)
            .then((response: AxiosResponse<Array<CoinContract>>) => {
                setCoins(response.data);
            });
    }, [])

    return (
        <MyCoinsListWrapper>
            {coins.map(coin =>
                <Coin key={coin.symbol} coin={coin}/>
            )}
        </MyCoinsListWrapper>
    );
};

export default MyCoinList;

const MyCoinsListWrapper = styled.div`
margin-top: 2em;
  display: flex;
  width: 80%;
  align-self: center;
  flex-wrap: wrap;
`;

